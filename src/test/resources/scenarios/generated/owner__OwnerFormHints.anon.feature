Feature: Owner Form Hints

  Scenario: TC_OWNER_001 Verify hint text on Add New Owner form
    Given I go to the main page
    When I click on the link with title "find owners"
    And I click on the link with text "Add Owner"
    Then I should see the text "All fields are required. Telephone must be numeric, up to 10 digits."

  Scenario: TC_OWNER_002 Verify hint text on Update Owner form
    Given I go to the main page
    When I click on the link with title "find owners"
    And I fill the field named "lastName" with value "Franklin"
    And I submit the form "search-owner-form"
    And I click on the link with text "Edit Owner"
    Then I should see the text "All fields are required. Telephone must be numeric, up to 10 digits."
