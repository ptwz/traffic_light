Feature: The system must be able to withstand communication issues in a safe and secure manner
	@wip
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
                Then the red light of both lights must be on permanently
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

	@wip
        Scenario: If the MQTT connection of a light becomes severed, the lights must resynchonize once the connection is restored
                Given I have an mqtt server
                And I have one traffic light called hangar with a controller
                And I have one traffic light called railroad
                When I turn the traffic light hangar on
                And I turn the traffic light railroad on
                And wait for hangar to settle
                And wait for railroad to settle
                Then the green light of hangar must be on permanently
                And the green light of railroad must be on permanently
                When I press the red button on the controller of hangar
                And wait for hangar to settle
                And wait for railroad to settle
                Then the red light of hangar must be on permanently
                And the red light of railroad must be on permanently
                When I press the green button on the controller of hangar
                And wait for hangar to settle
                And wait for railroad to settle
                Then the green light of hangar must be on permanently
                And the green light of railroad must be on permanently
