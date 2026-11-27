Feature: Owner Form Validation (Anonymous)

  Scenario: TC_OWNER_001 Verify hint text on Add Owner form
    Given I go to the find-owners page
    When I click on the link with text "Add Owner"
    Then I should see the "Owner" page
    And I should see the text "All fields are required. Telephone must be numeric, up to 10 digits."

  Scenario: TC_OWNER_002 Verify hint text on Update Owner form
    Given I go to the main page
    When I click on the link with title "find owners"
    And I fill the field named "lastName" with value "Franklin"
    And I submit the form "search-owner-form"
    When I click on the button with text "Edit Owner"
    Then I should see the "Owner" page
    And I should see the text "All fields are required. Telephone must be numeric, up to 10 digits."

  Scenario: TC_OWNER_003 Add Owner with valid 10-digit numeric telephone
    Given I go to the find-owners page
    When I click on the link with text "Add Owner"
    And I fill the field named "firstName" with value "John"
    And I fill the field named "lastName" with value "Doe"
    And I fill the field named "address" with value "123 Main St"
    And I fill the field named "city" with value "Anytown"
    And I fill the field named "telephone" with value "1234567890"
    And I click on the button with text "Add Owner"
    Then I should see the "Owner Information" page
    And I should see the text "John Doe"

  Scenario: TC_OWNER_005 Add Owner with telephone more than 10 digits
    Given I go to the find-owners page
    When I click on the link with text "Add Owner"
    And I fill the field named "firstName" with value "Alice"
    And I fill the field named "lastName" with value "Brown"
    And I fill the field named "address" with value "789 Pine Ln"
    And I fill the field named "city" with value "Somewhere"
    And I fill the field named "telephone" with value "12345678901"
    And I click on the button with text "Add Owner"
    Then I should see the "Owner" page
    And I should see the text "Telephone must be numeric, up to 10 digits."

  Scenario: TC_OWNER_006 Add Owner with telephone less than 10 digits (e.g., 9 digits)
    Given I go to the find-owners page
    When I click on the link with text "Add Owner"
    And I fill the field named "firstName" with value "Bob"
    And I fill the field named "lastName" with value "White"
    And I fill the field named "address" with value "101 Elm Rd"
    And I fill the field named "city" with value "Nowhere"
    And I fill the field named "telephone" with value "123456789"
    And I click on the button with text "Add Owner"
    Then I should see the "Owner Information" page
    And I should see the text "Bob White"

