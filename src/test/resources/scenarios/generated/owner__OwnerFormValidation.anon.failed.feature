Feature: Owner Form Validation (Anonymous)

  Scenario: TC_OWNER_004 Add Owner with non-numeric telephone
    Given I go to the find-owners page
    When I click on the link with text "Add Owner"
    And I fill the field named "firstName" with value "Jane"
    And I fill the field named "lastName" with value "Smith"
    And I fill the field named "address" with value "456 Oak Ave"
    And I fill the field named "city" with value "Otherville"
    And I fill the field named "telephone" with value "abcde12345"
    And I click on the button with text "Add Owner"
    Then I should see the "Owner" page
    And I should see the text "Telephone must be numeric, up to 10 digits."

  Scenario: TC_OWNER_007 Add Owner with empty telephone
    Given I go to the find-owners page
    When I click on the link with text "Add Owner"
    And I fill the field named "firstName" with value "Charlie"
    And I fill the field named "lastName" with value "Green"
    And I fill the field named "address" with value "202 Birch St"
    And I fill the field named "city" with value "Anyplace"
    And I clear the field named "telephone"
    And I click on the button with text "Add Owner"
    Then I should see the "Owner" page
    And I should see the text "may not be empty"
