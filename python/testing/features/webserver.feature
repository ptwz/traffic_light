
Feature: Webserver
        @wip
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
                Then the webserver indicates that <b> is alive
                Then the green light of hangar must be on permanently
                And the green light of garbenheim must be on permanently

                Examples:
                | a              | b                    |
                | hangar         | garbenheim           |
                | garbenheim     | hangar               |

