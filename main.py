#!/usr/bin/python
from functions import *

welcomeMessage()

firstin=input()
if firstin == "help":
    helpMessage()
else:
    run("lsblk")

# Taking user inputs
drive = input("Please type in the name of the Drive you want to flash: ")
iso = input("Please enter the path to your iso file: ")
verif = input("All data on your drive will be lost. Do you want to continue?[Y/n]: ")

if verif.lower() == "y":
    createBootable(drive,iso)
else:
    print("...................TASK ABORTED.....................")
