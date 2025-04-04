#include<iostream>
#include"../header files/messages.h"

using namespace std;

int welcomeMessage(){
	cout << "\nWELCOME TO FLASH DRIVE CREATOR FOR LINUX\n";
	cout << "==========================================================================\n";
	cout << "This is a very basic prototype of a flashdrive creator for linux that uses\ncommand-line arguments for functioning. This is an open-source project\ncreated by Antariksha Ray\n";
	cout << "Antariksha Ray GitHub profile: https://github.com/RayAntariksha \nSpecial thanks to Shibam Roy!(https://github.com/ShibamRoy9826) \nfor his invalueable contribution in this project." << endl;
	cout << "==========================================================================\n";
	cout << "In case of any corrupt drives or data loss, the creator and the\ncontributors of this project will not be responsible in any way.\nThis project is still under development." << endl;
	cout << "==========================================================================\n";
	cout << "Please type in 'help' for additional help or type in 'continue' to\ncontinue with the process\n";
	return 0;
}

int helpMessage() {

	cout << "This is a very basic prototype of a flashdrive creator for linux that uses\ncommand-line arguments for functioning. This is an open-source project\ncreated by Antariksha Ray.\n";
	cout << "==========================================================================\n";
	cout << "Availabel commands:" << endl;
	cout << "help          ---help\n";
	cout << "exit          ---To exit the program\n";
	cout << "continue      ---To procced with the process of flashing the drive\n";
	cout << "press enter to continue...";
	cin;
	return 0;
}