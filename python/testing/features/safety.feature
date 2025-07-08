Feature: Lamp check
        Scenario: If all bulbs work, the traffic light should boot into green
                Given I have one traffic light called hangar which has no communication stack running
                When I turn the traffic light hangar on
                And wait for hangar to settle
                Then the red light of hangar must be on permanently

        Scenario Outline: If one of the bulbs fails during bootup check mark this ans an error
                Given I have one traffic light called hangar which has no communication stack running
                And the <color> bulb of hangar is defective
                When I turn the traffic light hangaron
                And wait for hangar to settle
                Then the yellow light of hangar must try to flash in 2 second rhythm
