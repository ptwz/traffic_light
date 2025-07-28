Feature: The system must be able to withstand communication issues in a safe and secure manner
        Scenario Outline: Upon boot, the MQTT-server might not be reachable immediately
                Given I have an mqtt server coming up delayed by <time> seconds
                And I have one traffic light called hangar with a controller
                And I have one traffic light called railroad
                When I turn the traffic light hangar on
                And I turn the traffic light railroad on
                And wait for hangar to settle
                And wait for railroad to settle
                When I press the red button on the controller of hangar
                And wait for hangar to settle
                And wait for railroad to settle
                Then the red light of both lights must be on permanently
                When I press the green button on the controller of hangar
                And wait for hangar to settle
                And wait for railroad to settle
                Then the green light of both lights must be on permanently

                Examples:
                | time    |
                | 6       |
                | 10      |

        Scenario Outline: If any light has a broken MQTT connection, both light must indicate a communication failure
                Given I have an mqtt server
                And I have one traffic light called hangar with a controller
                And I have one traffic light called railroad
                When I turn the traffic light hangar on
                And I turn the traffic light railroad on
                And wait for hangar to settle
                And wait for railroad to settle
                And the communication of <a> is interrupted for <time> seconds
                Then the yellow light of <a> must try to flash in 2 second rhythm
                And the yellow light of <b> must try to flash in 2 second rhythm
                When the communication of <a> is restored
                And I wait for <a> to settle
                And wait for <b> to settle
                When I press the red button on the controller of hangar
                And wait for hangar to settle
                And wait for railroad to settle
                Then the red light of both lights must be on permanently
                When I press the green button on the controller of hangar
                And wait for hangar to settle
                And wait for railroad to settle
                Then the green light of both lights must be on permanently

                Examples:
                | a              | b                    | time    |
                | hangar         | railroad             | 6       |
                | railroad       | hangar               | 6       |
                | hangar         | railroad             | 10      |
                | railroad       | hangar               | 10      |
                | hangar         | railroad             | 60      |
                | railroad       | hangar               | 60      |

        Scenario Outline: While booting, the Pi's ttyS0 might garble data, cope with it properly
                Given I have an mqtt server
                And I have one traffic light called hangar with a controller
                And I have one traffic light called railroad
                And the PIC of <a> generates <time> seconds of garbled data 
                When I turn the traffic light hangar on
                And I turn the traffic light railroad on
                And I wait for <a> to settle
                And wait for <b> to settle
                When I press the red button on the controller of hangar
                And wait for hangar to settle
                And wait for railroad to settle
                Then the red light of both lights must be on permanently
                When I press the green button on the controller of hangar
                And wait for hangar to settle
                And wait for railroad to settle
                Then the green light of both lights must be on permanently

                Examples:
                | a              | b                    | time    |
                | hangar         | railroad             | 6       |
                | railroad       | hangar               | 6       |
                | hangar         | railroad             | 10      |
                | railroad       | hangar               | 10      |
                | hangar         | railroad             | 60      |
                | railroad       | hangar               | 60      |

