
Feature: Synchronization
        Scenario Outline: If two traffic lights start up, no matter in which order, they must synchronize
                Given I have an mqtt server
                And I have one traffic light called <a>
                And I have one traffic light called <b>
                When I turn the traffic light <a> on
                And I turn the traffic light <b> on <time> seconds later
                And wait for <a> to settle
                And wait for <b> to settle
                Then the green light of hangar must be on permanently
                And the green light of garbenheim must be on permanently

                Examples:
                | a              | b                    | time    |
                | hangar         | garbenheim           | 0       |
                | garbenheim     | hangar               | 0       |
                | hangar         | garbenheim           | 5       |
                | garbenheim     | hangar               | 5       |
                | hangar         | garbenheim           | 10      |
                | garbenheim     | hangar               | 10      |
                | hangar         | garbenheim           | 60      |
                | garbenheim     | hangar               | 60      |


        Scenario Outline: If two traffic lights start up, no matter in which order with a broken bulb, they must synchronize
                Given I have an mqtt server
                And I have one traffic light called <a>
                And I have one traffic light called <b>
                And the <color> bulb of <a> is defective
                When I turn the traffic light <b> on
                And I turn the traffic light <b> on 10 seconds later
                And wait for <a> to settle
                And wait for <b> to settle
                Then the yellow light of <a> must try to flash in 2 second rhythm
                And the yellow light of <b> must try to flash in 2 second rhythm

                Examples:
                | a              | b                    | color   |
                | hangar         | garbenheim           | red     |
                | garbenheim     | hangar               | red     |
                | hangar         | garbenheim           | yellow  |
                | garbenheim     | hangar               | yellow  |
                | hangar         | garbenheim           | green   |
                | garbenheim     | hangar               | green   |

