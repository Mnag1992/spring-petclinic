Feature: Owner Form Validation (Anonymous)

  Scenario: TC_OWNER_001 Verify telephone field hint message on Add Owner page
    Given I go to the main page
    When I click on the link with title "find owners"
    And I click on the link with text "Add Owner"
    Then I should see the text "All fields are required. Telephone must be numeric, up to 10 digits."

  Scenario: TC_OWNER_002 Add owner with valid 10-digit telephone number
    Given I go to the main page
    When I click on the link with title "find owners"
    And I click on the link with text "Add Owner"
    And I fill the field named "firstName" with value "Test"
    And I fill the field named "lastName" with value "User"
    And I fill the field named "address" with value "123 Main St"
    And I fill the field named "city" with value "Anytown"
    And I fill the field named "telephone" with value "1234567890"
    And I click on the button with text "Add Owner"
    Then I should see the "Owner Information" page
    And I should see the text "Test User"

  Scenario: TC_OWNER_003 Add owner with non-numeric telephone number
    Given I go to the main page
    When I click on the link with title "find owners"
    And I click on the link with text "Add Owner"
    And I fill the field named "firstName" with value "Invalid"
    And I fill the field named "lastName" with value "Phone"
    And I fill the field named "address" with value "456 Oak Ave"
    And I fill the field named "city" with value "Somecity"
    And I fill the field named "telephone" with value "abcde"
    And I click on the button with text "Add Owner"
    Then I should see the text "Telephone must be numeric, up to 10 digits"

  Scenario: TC_OWNER_004 Add owner with telephone number exceeding 10 digits
    Given I go to the main page
    When I click on the link with title "find owners"
    And I click on the link with text "Add Owner"
    And I fill the field named "firstName" with value "Long"
    And I fill the field named "lastName" with value "Number"
    And I fill the field named "address" with value "789 Pine Ln"
    And I fill the field named "city" with value "Othertown"
    And I fill the field named "telephone" with value "12345678901"
    And I click on the button with text "Add Owner"
    Then I should see the text "Telephone must be numeric, up to 10 digits"

  Scenario: TC_OWNER_006 Update owner with non-numeric telephone number
    Given I go to the main page
    When I click on the link with title "find owners"
    And I fill the field named "lastName" with value "Franklin"
    And I submit the form "search-owner-form"
    And I click on the link with text "Edit Owner"
    And I fill the field named "telephone" with value "xyz"
    And I click on the button with text "Update Owner"
    Then I should see the text "Telephone must be numeric, up to 10 digits"

  Scenario: TC_OWNER_007 Update owner with telephone number exceeding 10 digits
    Given I go to the main page
    When I click on the link with title "find owners"
    And I fill the field named "lastName" with value "Franklin"
    And I submit the form "search-owner-form"
    And I click on the link with text "Edit Owner"
    And I fill the field named "telephone" with value "98765432109"
    And I click on the button with text "Update Owner"
    Then I should see the text "Telephone must be numeric, up to 10 digits"
