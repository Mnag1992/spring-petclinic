Feature: Owner Telephone Validation

  Scenario: TC_OWNER_003 Create Owner with non-numeric telephone displays validation message
    Given I go to the main page
    When I click on the link with title "find owners"
    And I click on the button with text "Add Owner"
    And I fill the field named "firstName" with value "Test"
    And I fill the field named "lastName" with value "User"
    And I fill the field named "address" with value "123 Test St"
    And I fill the field named "city" with value "Testville"
    And I fill the field named "telephone" with value "abcde"
    And I click on the button with text "Add Owner"
    Then I should see the text "Telephone must be numeric, up to 10 digits"

  Scenario: TC_OWNER_004 Create Owner with telephone exceeding 10 digits displays validation message
    Given I go to the main page
    When I click on the link with title "find owners"
    And I click on the button with text "Add Owner"
    And I fill the field named "firstName" with value "Test"
    And I fill the field named "lastName" with value "User"
    And I fill the field named "address" with value "123 Test St"
    And I fill the field named "city" with value "Testville"
    And I fill the field named "telephone" with value "12345678901"
    And I click on the button with text "Add Owner"
    Then I should see the text "Telephone must be numeric, up to 10 digits"

  Scenario: TC_OWNER_005 Create Owner with valid 10-digit telephone is successful
    Given I go to the main page
    When I click on the link with title "find owners"
    And I click on the button with text "Add Owner"
    And I fill the field named "firstName" with value "New"
    And I fill the field named "lastName" with value "Owner"
    And I fill the field named "address" with value "456 New Rd"
    And I fill the field named "city" with value "Newtown"
    And I fill the field named "telephone" with value "1234567890"
    And I click on the button with text "Add Owner"
    Then I should see the "Owner Information" page
    And I should see the text "New Owner"
    And I should see the text "1234567890"

  Scenario: TC_OWNER_006 Update Owner with non-numeric telephone displays validation message
    Given I go to the main page
    When I click on the link with title "find owners"
    And I fill the field named "lastName" with value "Franklin"
    And I submit the form "search-owner-form"
    And I click on the button with text "Edit Owner"
    And I clear the field named "telephone"
    And I fill the field named "telephone" with value "invalid"
    And I click on the button with text "Update Owner"
    Then I should see the text "Telephone must be numeric, up to 10 digits"

  Scenario: TC_OWNER_007 Update Owner with valid 10-digit telephone is successful
    Given I go to the main page
    When I click on the link with title "find owners"
    And I fill the field named "lastName" with value "Franklin"
    And I submit the form "search-owner-form"
    And I click on the button with text "Edit Owner"
    And I clear the field named "telephone"
    And I fill the field named "telephone" with value "9876543210"
    And I click on the button with text "Update Owner"
    Then I should see the "Owner Information" page
    And I should see the text "George Franklin"
    And I should see the text "9876543210"
