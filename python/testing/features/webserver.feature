
Feature: Webserver
        Scenario Outline: The webserver provides a view of the lights states
                Given I have an mqtt server
                And I have one traffic light called <a>
                And I have one traffic light called <b>
                And I have a webserver
                When I turn the traffic light <a> on
                And I turn the traffic light <b> on
                And wait for <a> to settle
                And wait for <b> to settle
                Then the webserver indicates that <a> is alive
                And the webserver indicates that <b> is alive
                And the green light of hangar must be on permanently
                And the green light of garbenheim must be on permanently

                Examples:
                | a              | b                    |
                | hangar         | garbenheim           |
                | garbenheim     | hangar               |

        @wip
        Scenario Outline: If any light has a broken MQTT connection, both light must indicate a communication failure and Webserver should indicate it
                Given I have an mqtt server
                And I have one traffic light called hangar with a controller
                And I have one traffic light called railroad
                And I have a webserver
                When I turn the traffic light hangar on
                And I turn the traffic light railroad on
                And wait for hangar to settle
                And wait for railroad to settle
                Then the webserver indicates that <b> is alive
                When the light <a> crashed
                And wait for <b> to settle
                Then the yellow light of <b> must try to flash in 2 second rhythm
                And the webserver indicates that <a> is not alive
                When the light <a> is restarted
                And I wait for <a> to settle
                And wait for <b> to settle
                When I press the red button on the controller of hangar
                And wait for hangar to settle
                And wait for railroad to settle
                Then the red light of both lights must be on permanently
                And the webserver indicates that <a> is alive
                When I press the green button on the controller of hangar
                And wait for hangar to settle
                And wait for railroad to settle
                Then the green light of both lights must be on permanently
                And webserver indicates that <a> is alive
                And webserver indicates that <b> is alive

                Examples:
                | a              | b                    | time    |
                | hangar         | railroad             | 6       |
                | railroad       | hangar               | 6       |
                | hangar         | railroad             | 10      |
                | railroad       | hangar               | 10      |
                | hangar         | railroad             | 60      |
                | railroad       | hangar               | 60      |

