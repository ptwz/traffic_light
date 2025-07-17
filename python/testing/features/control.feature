
Feature: Remote control
        Scenario: If two traffic lights start up, and I press the control buttons,
                  both lights must follow the commanded state.
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
