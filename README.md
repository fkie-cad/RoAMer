# RoAMer

This repository is the home of RoAMer, the "Robust Automatic Malware Unpacker".
RoAMer has been developed by Thorsten Jenke, with code contributions by Daniel Plohmann.

It is a generic unpacker based on dynamic analysis. The paper has been presented on MALWARE 2019 and will be released soonish.

This is still a very early version. Expect updates soon :)

## Setup

### Compile
* clone git repo
* Install dependencies 
* execute `compile.bat` in cmd
* compiled version can be found in unpacker/dist, pewhitelister/dist, and receiver/dist

### Deployment

* start hardened VM
* copy PeHeaderWhitelister.exe to the VM (e.g. using `python -mSimpleHTTPServer`)
* run `PeHeaderWhitelister.exe C:\` in cmd and copy output of this script to the current VM's user home directory
* if you work with multiple VMs you have to assign static IP addresses and configure them in the config.py
* extract unpacker/dist/main.exe to unpacker/bin
* transfer receiver/dist/main.exe to VM
* start receiver ´main.exe´ in the VM within a command line terminal (cmd.exe) as an administrator 
* move desktop symbols so that the upper left corner is free
* create a shortcut to notepade as the first icon directly below the free space
* open notepad with the shortcut and move it over the notepad shortcut icon, then close notepad
* create snapshot and name it e.g. `init`
* check the host's config.py for the `SNAPSHOT_NAME` (e.g. `init`) and `VM_NAME` (e.g. `win7box`)

## How To Use

* Adjust config.py parameters as needed. The default configuration was the most successful as determined by the Thesis' evaluation.
* Start receiver within the VM before creating a saved machine state as snapshot. This component will later replace itself with the version of unpacker that is sent to it when RoAMer is executed.
* Just start /run.py <path_to_sample> and RoAMer will then do its magic in the VM and respond with the identified dumps.

## Dependencies

* Python 3.7 64bit
* pyinstaller
* pywin32: https://sourceforge.net/projects/pywin32/files/pywin32/

## Sources
* The hooks have been designed with the help of https://www.apriorit.com/dev-blog/160-apihooks
