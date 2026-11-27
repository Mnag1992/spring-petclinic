Feature: Owner Form Hints

  Scenario: TC_OWNER_001 Verify telephone field hint on Add Owner page
    Given I go to the main page
    When I click on the link with title "find owners"
    And I click on the button with text "Add Owner"
    Then I should see the text "All fields are required. Telephone must be numeric, up to 10 digits."
