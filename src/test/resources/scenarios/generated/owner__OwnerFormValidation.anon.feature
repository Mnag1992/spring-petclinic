Feature: Owner Form Validation

  Scenario: TC_OWNER_002 Verify telephone field validation with non-numeric input when adding a new owner
    Given I go to the main page
    When I click on the link with title "find owners"
    And I click on the button with text "Add Owner"
    And I fill the field named "firstName" with value "Test"
    And I fill the field named "lastName" with value "Owner"
    And I fill the field named "address" with value "123 Test St"
    And I fill the field named "city" with value "Testville"
    And I fill the field named "telephone" with value "abc"
    And I click on the button with text "Add Owner"
    Then I should see the text "Telephone must be numeric, up to 10 digits."

  Scenario: TC_OWNER_003 Verify telephone field validation with more than 10 digits when adding a new owner
    Given I go to the main page
    When I click on the link with title "find owners"
    And I click on the button with text "Add Owner"
    And I fill the field named "firstName" with value "Test"
    And I fill the field named "lastName" with value "Owner"
    And I fill the field named "address" with value "123 Test St"
    And I fill the field named "city" with value "Testville"
    And I fill the field named "telephone" with value "12345678901"
    And I click on the button with text "Add Owner"
    Then I should see the text "Telephone must be numeric, up to 10 digits."

  Scenario: TC_OWNER_004 Verify telephone field validation with empty input when adding a new owner
    Given I go to the main page
    When I click on the link with title "find owners"
    And I click on the button with text "Add Owner"
    And I fill the field named "firstName" with value "Test"
    And I fill the field named "lastName" with value "Owner"
    And I fill the field named "address" with value "123 Test St"
    And I fill the field named "city" with value "Testville"
    And I clear the field named "telephone"
    And I click on the button with text "Add Owner"
    Then I should see the text "Telephone must be numeric, up to 10 digits."

  Scenario: TC_OWNER_008 Verify telephone field validation with more than 10 digits when updating an existing owner
    Given I go to the main page
    When I click on the link with title "find owners"
    And I fill the field named "lastName" with value "Franklin"
    And I submit the form "search-owner-form"
    And I click on the button with text "Edit Owner"
    And I fill the field named "telephone" with value "12345678901"
    And I click on the button with text "Update Owner"
    Then I should see the text "Telephone must be numeric, up to 10 digits."

