########################################################################
# $Id: JobStateUpdateHandler.py,v 1.14 2008/02/27 20:18:49 atsareg Exp $
########################################################################

""" JobStateUpdateHandler is the implementation of the Job State updating
    service in the DISET framework

    The following methods are available in the Service interface

    setJobStatus()

"""

__RCSID__ = "$Id: JobStateUpdateHandler.py,v 1.14 2008/02/27 20:18:49 atsareg Exp $"

from types import *
from DIRAC.Core.DISET.RequestHandler import RequestHandler
from DIRAC import gLogger, S_OK, S_ERROR
from DIRAC.WorkloadManagementSystem.DB.JobDB import JobDB
from DIRAC.WorkloadManagementSystem.DB.JobLoggingDB import JobLoggingDB

# This is a global instance of the JobDB class
jobDB = False
logDB = False

def initializeJobStateUpdateHandler( serviceInfo ):

  global jobDB
  global logDB
  jobDB = JobDB()
  logDB = JobLoggingDB()
  return S_OK()

class JobStateUpdateHandler( RequestHandler ):

  ###########################################################################
  types_setJobStatus = [IntType,StringType,StringType,StringType]
  def export_setJobStatus(self,jobID,status,minorStatus,source='Unknown',datetime=None):
    """ Set the major and minor status for job specified by its JobId.
        Set optionally the status date and source component which sends the
        status information.
    """

    if status:
      result = jobDB.setJobAttribute(jobID,'Status',status)
      if not result['OK']:
        return result
    if minorStatus:
      result = jobDB.setJobAttribute(jobID,'MinorStatus',minorStatus,True)
      if not result['OK']:
        return result

    result = jobDB.getJobAttributes(jobID, ['Status','MinorStatus'] )
    if not result['OK']:
      return result

    status = result['Value']['Status']
    minorStatus = result['Value']['MinorStatus']
    if datetime:
      result = logDB.addLoggingRecord(jobID,status,minorStatus,datetime,source)
    else:
      result = logDB.addLoggingRecord(jobID,status,minorStatus,source=source)

    return result

  ###########################################################################
  types_setJobSite = [IntType,StringType]
  def export_setJobSite(self,jobID,site):
    """Allows the site attribute to be set for a job specified by its jobID.
    """
    result = jobDB.setJobAttribute(jobID,'Site',site)
    return result

  ###########################################################################
  types_setJobApplicationStatus = [IntType,StringType,StringType]
  def export_setJobApplicationStatus(self,jobID,appStatus,source='Unknown'):
    """ Set the application status for job specified by its JobId.
    """
    result = jobDB.setJobAttribute(jobID,'ApplicationStatus',appStatus)
    if not result['OK']:
      return result

    result = jobDB.getJobAttributes(jobID, ['Status','MinorStatus'] )
    if not result['OK']:
      return result

    status = result['Value']['Status']
    minorStatus = result['Value']['MinorStatus']
    result = logDB.addLoggingRecord(jobID,status,minorStatus,appStatus,source=source)
    return result

  ###########################################################################
  types_setJobParameter = [IntType,StringType,StringType]
  def export_setJobParameter(self,jobID,name,value):
    """ Set arbitrary parameter specified by name/value pair
        for job specified by its JobId
    """

    result = jobDB.setJobParameter(jobID,name,value)
    return result

  ###########################################################################
  types_setJobParameters = [IntType,ListType]
  def export_setJobParameters(self,jobID,parameters):
    """ Set arbitrary parameters specified by a list of name/value pairs
        for job specified by its JobId
    """

    OK = True
    for name,value in parameters:
      result = jobDB.setJobParameter(jobID,name,value)
      if not result['OK']:
        OK = False

    if OK:
      return S_OK('All parameters stored for job')
    else:
      return S_ERROR('Failed to store some of the parameters')

  ###########################################################################
  types_sendHeartBeat = [IntType, DictType, DictType]
  def export_sendHeartBeat(self,jobID,dynamicData,staticData):
    """ Send a heart beat sign of life for a job jobID
    """

    result = jobDB.setHeartBeatData(jobID,staticData, dynamicData)
    if not result['OK']:
      gLogger.error('Failed to set the heart beat data for job %d ' % jobID)

    # Restore the Running status if necessary
    result = jobDB.getJobAttributes(jobID,['Status'])
    if not result['OK']:
      return result

    status = result['Value']['Status']
    if status == "Stalled":
      result = jobDB.setJobAttribute(jobID,'Status','Running',True)
      if not result['OK']:
        gLogger.error('Failed to restore the job status to Running')

    jobMessageDict = {}
    result = jobDB.getJobCommand(jobID)
    if result['OK']:
      jobMessageDict = result['Value']

    return S_OK(jobMessageDict)

