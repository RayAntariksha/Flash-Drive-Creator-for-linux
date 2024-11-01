#!/usr/bin/python
import os


welcome="""
Welcome to the Flash Drive Creator!
----------------------------------

Type 'help' for help or 'exit' to close this application\n
"""

helpmsg="""
 Press enter to see the available drives and continue with the installation
"""

def run(cmd):
  os.system(command=cmd)
  
def createBootable(drive,iso):
    # Step 1:
    # Unmount drive
    run("sudo umount "+ drive)

    # Step 2:
    # Create the Bootable USB

    #print("sudo dd if=" + iso + " of="+ drive +" bs=4M status=progress")

    run("sudo dd if=" + iso + " of=/dev/sdX bs=4M status=progress")

    # Step 4:
    # Sync and eject
    run("sudo sync")

def welcomeMessage():
  print(welcome)
def helpMessage():
  print(helpmsg)

