########################################################################
# $HeadURL$
########################################################################
""" The FileCatalogClient is a class representing the client of the DIRAC File Catalog  """

__RCSID__ = "$Id$"

from types import ListType, DictType
import os
from DIRAC import S_OK, S_ERROR
from DIRAC.ConfigurationSystem.Client.Helpers.Registry import getVOMSAttributeForGroup, getDNForUsername
from DIRAC.DataManagementSystem.Utilities.CatalogUtilities import checkCatalogArguments
from DIRAC.Core.DISET.RPCClient import RPCClient

class FileCatalogClient( object ):
  """ Client code to the DIRAC File Catalogue
  """
  def __init__( self, url = None, **kwargs ):
    """ Constructor function.
    """
    self.__kwargs = kwargs
    self.server = 'DataManagement/FileCatalog'
    if url:
      self.server = url
    self.available = False
    
  def __getRPC( self, rpc = None, url = '', timeout = 600 ):
    """ Return RPCClient object to url
    """
    if not rpc:
      if not url:
        url = self.server
      self.__kwargs.setdefault( 'timeout', timeout )
      rpc = RPCClient( url, **self.__kwargs )
    return rpc  

  def isOK( self, timeout = 120 ):
    """ Check that the service is OK
    """
    if not self.available:
      rpcClient = self.__getRPC( timeout = timeout )
      res = rpcClient.isOK()
      if not res['OK']:
        self.available = False
      else:
        self.available = True
    return S_OK( self.available )

  def hasCatalogMethod( self, methodName ):
    """ Check of a method with the given name is implemented
    :param str methodName: the name of the method to check
    :return: boolean Flag
    """
    return hasattr( self, methodName )

  @checkCatalogArguments
  def getReplicas( self, lfns, allStatus = False, timeout = 120 ):
    """ Get the replicas of the given files
    """
    rpcClient = self.__getRPC( timeout = timeout )
    result = rpcClient.getReplicas( lfns, allStatus )
    if not result['OK']:
      return result

    lfnDict = result['Value']
    seDict = result['Value'].get( 'SEPrefixes', {} )
    for lfn in lfnDict['Successful']:
      for se in lfnDict['Successful'][lfn]:
        if not lfnDict['Successful'][lfn][se] and se in seDict:
          lfnDict['Successful'][lfn][se] = seDict[se] + lfn

    return S_OK( lfnDict )

  @checkCatalogArguments
  def setReplicaProblematic( self, lfns, revert = False ):
    """
      Set replicas to problematic.
      :param lfn lfns has to be formated this way :
                  { lfn : { se1 : pfn1, se2 : pfn2, ...}, ...}
      :param revert If True, remove the problematic flag

      :return { successful : { lfn : [ ses ] } : failed : { lfn : { se : msg } } }
    """

    # This method does a batch treatment because the setReplicaStatus can only take one replica per lfn at once
    #
    # Illustration :
    #
    # lfns {'L2': {'S1': 'P3'}, 'L3': {'S3': 'P5', 'S2': 'P4', 'S4': 'P6'}, 'L1': {'S2': 'P2', 'S1': 'P1'}}
    #
    # loop1: lfnSEs {'L2': ['S1'], 'L3': ['S3', 'S2', 'S4'], 'L1': ['S2', 'S1']}
    # loop1 : batch {'L2': {'Status': 'P', 'SE': 'S1', 'PFN': 'P3'},
    #                'L3': {'Status': 'P', 'SE': 'S4', 'PFN': 'P6'},
    #                'L1': {'Status': 'P', 'SE': 'S1', 'PFN': 'P1'}}
    #
    # loop2: lfnSEs {'L2': [], 'L3': ['S3', 'S2'], 'L1': ['S2']}
    # loop2 : batch {'L3': {'Status': 'P', 'SE': 'S2', 'PFN': 'P4'}, 'L1': {'Status': 'P', 'SE': 'S2', 'PFN': 'P2'}}
    #
    # loop3: lfnSEs {'L3': ['S3'], 'L1': []}
    # loop3 : batch {'L3': {'Status': 'P', 'SE': 'S3', 'PFN': 'P5'}}
    #
    # loop4: lfnSEs {'L3': []}
    # loop4 : batch {}


    successful = {}
    failed = {}

    status = 'AprioriGood' if revert else 'Trash'

    # { lfn : [ se1, se2, ...], ...}
    lfnsSEs = dict( ( lfn, [se for se in lfns[lfn]] ) for lfn in lfns )

    while lfnsSEs:

      # { lfn : { 'SE' : se1, 'PFN' : pfn1, 'Status' : status }, ... }
      batch = {}

      for lfn in lfnsSEs.keys():
        # If there are still some Replicas (SE) for the given LFN, we put it in the next batch
        # else we remove the entry from the lfnsSEs dict
        if lfnsSEs[lfn]:
          se = lfnsSEs[lfn].pop()
          batch[lfn] = { 'SE' : se, 'PFN' : lfns[lfn][se], 'Status' : status }
        else:
          del lfnsSEs[lfn]

      # Happens when there is nothing to treat anymore
      if not batch:
        break

      res = self.setReplicaStatus( batch )
      if not res['OK']:
        for lfn in batch:
          failed.setdefault( lfn, {} )[batch[lfn]['SE']] = res['Message']
        continue

      for lfn in res['Value']['Failed']:
        failed.setdefault( lfn, {} )[batch[lfn]['SE']] = res['Value']['Failed'][lfn]

      for lfn in res['Value']['Successful']:
        successful.setdefault( lfn, [] ).append( batch[lfn]['SE'] )

    return S_OK( {'Successful' : successful, 'Failed': failed} )

  @checkCatalogArguments
  def listDirectory( self, lfn, verbose = False, timeout = 120 ):
    """ List the given directory's contents
    """
    rpcClient = self.__getRPC( timeout = timeout )
    result = rpcClient.listDirectory( lfn, verbose )
    if not result['OK']:
      return result
    # Force returned directory entries to be LFNs
    for entryType in ['Files', 'SubDirs', 'Links']:
      for path in result['Value']['Successful']:
        entryDict = result['Value']['Successful'][path][entryType]
        for fname in entryDict.keys():
          detailsDict = entryDict.pop( fname )
          lfn = os.path.join( path, os.path.basename( fname ) )
          entryDict[lfn] = detailsDict
    return result

  @checkCatalogArguments
  def getDirectoryMetadata( self, lfns, timeout = 120 ):
    ''' Get standard directory metadata
    '''
    rpcClient = self.__getRPC( timeout = timeout )
    result = rpcClient.getDirectoryMetadata( lfns )
    if not result['OK']:
      return result
    # Add some useful fields
    for path in result['Value']['Successful']:
      owner = result['Value']['Successful'][path]['Owner']
      group = result['Value']['Successful'][path]['OwnerGroup']
      res = getDNForUsername( owner )
      if res['OK']:
        result['Value']['Successful'][path]['OwnerDN'] = res['Value'][0]
      else:
        result['Value']['Successful'][path]['OwnerDN'] = ''
      result['Value']['Successful'][path]['OwnerRole'] = getVOMSAttributeForGroup( group )
    return result

  @checkCatalogArguments
  def removeDirectory( self, lfn, recursive = False, timeout = 120 ):
    """ Remove the directory from the File Catalog. The recursive keyword is for the ineterface.
    """
    rpcClient = self.__getRPC( timeout = timeout )
    return rpcClient.removeDirectory( lfn )

  @checkCatalogArguments
  def getDirectoryReplicas( self, lfns, allStatus = False, timeout = 120 ):
    """ Find all the given directories' replicas
    """
    rpcClient = self.__getRPC( timeout = timeout )
    result = rpcClient.getDirectoryReplicas( lfns, allStatus )
    if not result['OK']:
      return result

    seDict = result['Value'].get( 'SEPrefixes', {} )
    for path in result['Value']['Successful']:
      pathDict = result['Value']['Successful'][path]
      for fname in pathDict.keys():
        detailsDict = pathDict.pop( fname )
        lfn = '%s/%s' % ( path, os.path.basename( fname ) )
        for se in detailsDict:
          if not detailsDict[se] and se in seDict:
            detailsDict[se] = seDict[se] + lfn
        pathDict[lfn] = detailsDict
    return result

  def findFilesByMetadata( self, metaDict, path = '/', timeout = 120 ):
    """ Find files given the meta data query and the path
    """
    rpcClient = self.__getRPC( timeout = timeout )
    result = rpcClient.findFilesByMetadata( metaDict, path )
    if not result['OK']:
      return result
    if type( result['Value'] ) == ListType:
      return result
    elif type( result['Value'] ) == DictType:
      # Process into the lfn list
      fileList = []
      for dir_, fList in result['Value'].items():
        for fi in fList:
          fileList.append( dir_ + '/' + fi )
      result['Value'] = fileList    
      return result
    else:
      return S_ERROR( 'Illegal return value type %s' % type( result['Value'] ) )

  @checkCatalogArguments
  def getFileUserMetadata( self, path, timeout = 120 ):
    """Get the meta data attached to a file, but also to
    the its corresponding directory
    """
    directory = "/".join( path.split( "/" )[:-1] )
    rpcClient = self.__getRPC( timeout = timeout )
    result = rpcClient.getFileUserMetadata( path )
    if not result['OK']:
      return result
    fmeta = result['Value']
    result = rpcClient.getDirectoryUserMetadata( directory )
    if not result['OK']:
      return result
    fmeta.update(result['Value'])
    
    return S_OK(fmeta)

  ########################################################################
  # Path operations (not updated)
  #

  @checkCatalogArguments
  def changePathOwner( self, lfns, recursive = False, timeout = 120 ):
    """ Get replica info for the given list of LFNs
    """
    return self.__getRPC( timeout = timeout ).changePathOwner( lfns, recursive )

  @checkCatalogArguments
  def changePathGroup( self, lfns, recursive = False, timeout = 120 ):
    """ Get replica info for the given list of LFNs
    """
    return self.__getRPC( timeout = timeout ).changePathGroup( lfns, recursive )

  @checkCatalogArguments
  def changePathMode( self, lfns, recursive = False, timeout = 120 ):
    """ Get replica info for the given list of LFNs
    """
    return self.__getRPC( timeout = timeout ).changePathMode( lfns, recursive )

  ########################################################################
  # ACL Operations
  #

  @checkCatalogArguments
  def getPathPermissions( self, lfns, timeout = 120 ):
    """ Determine the ACL information for a supplied path
    """
    return self.__getRPC( timeout = timeout ).getPathPermissions( lfns )

  @checkCatalogArguments
  def hasAccess( self, paths, opType, timeout = 120 ):
    """ Determine if the given op can be performed on the paths
        The OpType is all the operations exported
    """
    return self.__getRPC( timeout = timeout ).hasAccess( opType, paths )


  ###################################################################
  #
  #  User/Group write operations
  #


  def addUser( self, userName, timeout = 120 ):
    """ Add a new user to the File Catalog """
    return self.__getRPC( timeout = timeout ).addUser( userName )


  def deleteUser( self, userName, timeout = 120 ):
    """ Delete user from the File Catalog """
    return self.__getRPC( timeout = timeout ).deleteUser( userName )


  def addGroup( self, groupName, timeout = 120 ):
    """ Add a new group to the File Catalog """
    return self.__getRPC( timeout = timeout ).addGroup( groupName )


  def deleteGroup( self, groupName, timeout = 120 ):
    """ Delete group from the File Catalog """
    return self.__getRPC( timeout = timeout ).deleteGroup( groupName )

  ###################################################################
  #
  #  User/Group read operations
  #


  def getUsers( self, timeout = 120 ):
    """ Get all the users defined in the File Catalog """
    return self.__getRPC( timeout = timeout ).getUsers()

  def getGroups( self, timeout = 120 ):
    """ Get all the groups defined in the File Catalog """
    return self.__getRPC( timeout = timeout ).getGroups()

  ########################################################################
  #
  # Path read operations
  #

  @checkCatalogArguments
  def exists( self, lfns, timeout = 120 ):
    """ Check whether the supplied paths exists """
    return self.__getRPC( timeout = timeout ).exists( lfns )

  ########################################################################
  #
  # File write operations
  #

  @checkCatalogArguments
  def addFile( self, lfns, timeout = 120 ):
    """ Register supplied files """

    return self.__getRPC( timeout = timeout ).addFile( lfns )


  @checkCatalogArguments
  def removeFile( self, lfns, timeout = 120 ):
    """ Remove the supplied lfns """
    return self.__getRPC( timeout = timeout ).removeFile( lfns )


  @checkCatalogArguments
  def setFileStatus( self, lfns, timeout = 120 ):
    """ Remove the supplied lfns """
    return self.__getRPC( timeout = timeout ).setFileStatus( lfns )

  @checkCatalogArguments
  def addReplica( self, lfns, timeout = 120 ):
    """ Register supplied replicas """
    return self.__getRPC( timeout = timeout ).addReplica( lfns )

  @checkCatalogArguments
  def removeReplica( self, lfns, timeout = 120 ):
    """ Remove the supplied replicas """
    return self.__getRPC( timeout = timeout ).removeReplica( lfns )


  @checkCatalogArguments
  def setReplicaStatus( self, lfns, timeout = 120 ):
    """ Set the status for the supplied replicas """
    return self.__getRPC( timeout = timeout ).setReplicaStatus( lfns )

  @checkCatalogArguments
  def setReplicaHost( self, lfns, timeout = 120 ):
    """ Change the registered SE for the supplied replicas """
    return self.__getRPC( timeout = timeout ).setReplicaHost( lfns )

  @checkCatalogArguments
  def addFileAncestors( self, lfns, timeout = 120 ):
    """ Add file ancestor information for the given list of LFNs """
    return self.__getRPC( timeout = timeout ).addFileAncestors( lfns )

  ########################################################################
  #
  # File read operations
  #

  @checkCatalogArguments
  def isFile( self, lfns, timeout = 120 ):
    """ Check whether the supplied lfns are files """
    return self.__getRPC( timeout = timeout ).isFile( lfns )

  @checkCatalogArguments
  def getFileSize( self, lfns, timeout = 120 ):
    """ Get the size associated to supplied lfns """
    return self.__getRPC( timeout = timeout ).getFileSize( lfns )

  @checkCatalogArguments
  def getFileMetadata( self, lfns, timeout = 120 ):
    """ Get the metadata associated to supplied lfns """
    return self.__getRPC( timeout = timeout ).getFileMetadata( lfns )



  @checkCatalogArguments
  def getReplicaStatus( self, lfns, timeout = 120 ):
    """ Get the status for the supplied replicas """
    return self.__getRPC( timeout = timeout ).getReplicaStatus( lfns )

  @checkCatalogArguments
  def getFileAncestors( self, lfns, depths, timeout = 120 ):
    """ Get the status for the supplied replicas """
    return self.__getRPC( timeout = timeout ).getFileAncestors( lfns, depths )

  @checkCatalogArguments
  def getFileDescendents( self, lfns, depths, timeout = 120 ):
    """ Get the status for the supplied replicas """
    return self.__getRPC( timeout = timeout ).getFileDescendents( lfns, depths )

  @checkCatalogArguments
  def getLFNForGUID( self, guids, timeout = 120 ):
    """Get the matching lfns for given guids"""
    return self.__getRPC( timeout = timeout ).getLFNForGUID( guids )

  ########################################################################
  #
  # Directory write operations
  #

  @checkCatalogArguments
  def createDirectory( self, lfns, timeout = 120 ):
    """ Create the supplied directories """
    return self.__getRPC( timeout = timeout ).createDirectory( lfns )


  ########################################################################
  #
  # Directory read operations
  #


  @checkCatalogArguments
  def isDirectory( self, lfns, timeout = 120 ):
    """ Determine whether supplied path is a directory """
    return self.__getRPC( timeout = timeout ).isDirectory( lfns )


  @checkCatalogArguments
  def getDirectorySize( self, lfns, longOut = False, fromFiles = False, timeout = 120 ):
    """ Get the size of the supplied directory """
    return self.__getRPC( timeout = timeout ).getDirectorySize( lfns, longOut, fromFiles )



  ########################################################################
  #
  # Administrative database operations
  #


  def getCatalogCounters( self, timeout = 120 ):
    """ Get the number of registered directories, files and replicas in various tables """
    return self.__getRPC( timeout = timeout ).getCatalogCounters()


  def rebuildDirectoryUsage( self, timeout = 120 ):
    """ Rebuild DirectoryUsage table from scratch """
    return self.__getRPC( timeout = timeout ).rebuildDirectoryUsage()


  def repairCatalog( self, timeout = 120 ):
    """ Repair the catalog inconsistencies """
    return self.__getRPC( timeout = timeout ).repairCatalog()

  ########################################################################
  # Metadata Catalog Operations
  #


  def addMetadataField( self, fieldName, fieldType, metaType = '-d', timeout = 120 ):
    """ Add a new metadata field of the given type
    """
    return self.__getRPC( timeout = timeout ).addMetadataField( fieldName, fieldType, metaType )


  def deleteMetadataField( self, fieldName, timeout = 120 ):
    """ Delete the metadata field
    """
    return self.__getRPC( timeout = timeout ).deleteMetadataField( fieldName )



  def getMetadataFields( self, timeout = 120 ):
    """ Get all the metadata fields
    """
    return self.__getRPC( timeout = timeout ).getMetadataFields()



  def setMetadata( self, path, metadatadict, timeout = 120 ):
    """ Set metadata parameter for the given path
    """
    return self.__getRPC( timeout = timeout ).setMetadata( path, metadatadict )


  def setMetadataBulk( self, pathMetadataDict, timeout = 120 ):
    """ Set metadata parameter for the given path
    """
    return self.__getRPC( timeout = timeout ).setMetadataBulk( pathMetadataDict )


  def removeMetadata( self, pathMetadataDict, timeout = 120 ):
    """ Remove the specified metadata for the given path
    """
    return self.__getRPC( timeout = timeout ).removeMetadata( pathMetadataDict )


  def getDirectoryUserMetadata( self, path, timeout = 120 ):
    """ Get all the metadata valid for the given directory path
    """
    return self.__getRPC( timeout = timeout ).dmeta.getDirectoryMetadata( path )




  def findDirectoriesByMetadata( self, metaDict, path = '/', timeout = 120 ):
    """ Find all the directories satisfying the given metadata set
    """
    return self.__getRPC( timeout = timeout ).findDirectoriesByMetadata ( metaDict, path )




  def getReplicasByMetadata( self, metaDict, path = '/', allStatus = False, timeout = 120 ):
    """ Find all the files satisfying the given metadata set
    """
    return self.__getRPC( timeout = timeout ).getReplicasByMetadata( metaDict, path, allStatus )


  def findFilesByMetadataDetailed( self, metaDict, path = '/', timeout = 120 ):
    """ Find all the files satisfying the given metadata set
    """
    return self.__getRPC( timeout = timeout ).findFilesByMetadataDetailed( metaDict, path )



  def findFilesByMetadataWeb( self, metaDict, path, startItem, maxItems, timeout = 120 ):
    """ Find files satisfying the given metadata set
    """
    return self.__getRPC( timeout = timeout ).findFilesByMetadataWeb( metaDict, path, startItem, maxItems )



  def getCompatibleMetadata( self, metaDict, path = '/', timeout = 120 ):
    """ Get metadata values compatible with the given metadata subset
    """
    return self.__getRPC( timeout = timeout ).getCompatibleMetadata( metaDict, path )


  def addMetadataSet( self, setName, setDict, timeout = 120 ):
    """ Add a new metadata set
    """
    return self.__getRPC( timeout = timeout ).addMetadataSet( setName, setDict )


  def getMetadataSet( self, setName, expandFlag, timeout = 120 ):
    """ Add a new metadata set
    """
    return self.__getRPC( timeout = timeout ).getMetadataSet( setName, expandFlag )

#########################################################################################
#
#  Dataset manipulation methods
#

  @checkCatalogArguments
  def addDataset( self, datasets, timeout = 120 ):
    """ Add a new dynamic dataset defined by its meta query
    """
    return self.__getRPC( timeout = timeout ).addDataset( datasets )

  @checkCatalogArguments
  def addDatasetAnnotation( self, datasetDict, timeout = 120 ):
    """ Add annotation to an already created dataset
    """
    return self.__getRPC( timeout = timeout ).addDatasetAnnotation( datasetDict )

  @checkCatalogArguments
  def removeDataset( self, datasets, timeout = 120 ):
    """ Check the given dynamic dataset for changes since its definition
    """
    return self.__getRPC( timeout = timeout ).removeDataset( datasets )

  @checkCatalogArguments
  def checkDataset( self, datasets, timeout = 120 ):
    """ Check the given dynamic dataset for changes since its definition
    """
    return self.__getRPC( timeout = timeout ).checkDataset( datasets )

  @checkCatalogArguments
  def updateDataset( self, datasets, timeout = 120 ):
    """ Update the given dynamic dataset for changes since its definition
    """
    return self.__getRPC( timeout = timeout ).updateDataset( datasets )

  @checkCatalogArguments
  def getDatasets( self, datasets, timeout = 120 ):
    """ Get parameters of the given dynamic dataset as they are stored in the database
    """
    return self.__getRPC( timeout = timeout ).getDatasets( datasets )

  @checkCatalogArguments
  def getDatasetParameters( self, datasets, timeout = 120 ):
    """ Get parameters of the given dynamic dataset as they are stored in the database
    """
    return self.__getRPC( timeout = timeout ).getDatasetParameters( datasets )

  @checkCatalogArguments
  def getDatasetAnnotation( self, datasets, timeout = 120 ):
    """ Get annotation of the given datasets
    """
    return self.__getRPC( timeout = timeout ).getDatasetAnnotation( datasets )

  @checkCatalogArguments
  def freezeDataset( self, datasets, timeout = 120 ):
    """ Freeze the contents of the dataset making it effectively static
    """
    return self.__getRPC( timeout = timeout ).freezeDataset( datasets )

  @checkCatalogArguments
  def releaseDataset( self, datasets, timeout = 120 ):
    """ Release the contents of the frozen dataset allowing changes in its contents
    """
    return self.__getRPC( timeout = timeout ).releaseDataset( datasets )

  @checkCatalogArguments
  def getDatasetFiles( self, datasets, timeout = 120 ):
    """ Get lfns in the given dataset
    two lines !
    """
    return self.__getRPC( timeout = timeout ).getDatasetFiles( datasets )



