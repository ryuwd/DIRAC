#!/usr/bin/env python
"""
  Get parameters assigned to the CE
"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

__RCSID__ = "$Id$"

import json
from DIRAC.Core.Base import Script
from DIRAC.Core.Utilities.DIRACScript import DIRACScript


@DIRACScript()
def main():
  ceName = ''
  Queue = ''
  Site = ''

  from DIRAC import gLogger, exit as DIRACExit
  from DIRAC.ConfigurationSystem.Client.Helpers import Resources

  Script.setUsageMessage('\n'.join(['Get the parameters of a CE',
                                    'Usage:',
                                    '  %s [option]... [cfgfile]' % Script.scriptName,
                                    'Arguments:',
                                    '  cfgfile: DIRAC Cfg with description of the configuration (optional)']))

  def setCEName(args):
    global ceName
    ceName = args

  def setSite(args):
    global Site
    Site = args

  def setQueue(args):
    global Queue
    Queue = args

  Script.registerSwitch("N:", "Name=", "Computing Element Name (Mandatory)", setCEName)
  Script.registerSwitch("S:", "Site=", "Site Name (Mandatory)", setSite)
  Script.registerSwitch("Q:", "Queue=", "Queue Name (Mandatory)", setQueue)

  Script.parseCommandLine(ignoreErrors=True)
  args = Script.getExtraCLICFGFiles()

  if len(args) > 1:
    Script.showHelp(exitCode=1)

  result = Resources.getQueue(Site, ceName, Queue)

  if not result['OK']:
    gLogger.error("Could not retrieve resource parameters", ": " + result['Message'])
    DIRACExit(1)
  gLogger.notice(json.dumps(result['Value']))


if __name__ == "__main__":
  main()
