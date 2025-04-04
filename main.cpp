#include <iostream>
#include<string>
#include"header files/messages.h"
#include"header files/flash.h"

using namespace std;

int main() {
    string initialInput;
    welcomeMessage();
    cout << ">>";
    cin >> initialInput;

    if (initialInput == "help") {
        helpMessage();
    }
    else if (initialInput == "continue") {

        cout << "Here are all the drives connected to the pc right now." << endl;
        flash();
    }else if(initialInput == "exit") {
        exit(0);
    }
    else {
        cout << "'" << initialInput << "'" << " is not a recognised option";
    }
    system("pause");

    return main();
}