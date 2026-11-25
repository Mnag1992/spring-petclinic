Feature: Owner Form Validation

  Scenario: TC_OWNER_001 Display of telephone field hint on Add Owner form
    Given I go to the main page
    When I click on the link with title "find owners"
    And I click on the link with text "Add Owner"
    Then I should see the text "All fields are required. Telephone must be numeric, up to 10 digits."

  Scenario: TC_OWNER_003 Create owner with non-numeric telephone number
    Given I go to the main page
    When I click on the link with title "find owners"
    And I click on the link with text "Add Owner"
    And I fill the field named "firstName" with value "Jane"
    And I fill the field named "lastName" with value "Smith"
    And I fill the field named "address" with value "456 Oak Ave"
    And I fill the field named "city" with value "Someville"
    And I fill the field named "telephone" with value "abcde"
    And I click on the button with text "Add Owner"
    Then I should see the "Owner" page
    And I should see the text "Telephone must be numeric, up to 10 digits"

  Scenario: TC_OWNER_008 Update owner with non-numeric telephone number
    Given I go to the main page
    When I click on the link with title "find owners"
    And I fill the field named "lastName" with value "Franklin"
    And I submit the form "search-owner-form"
    And I click on the link with text "Edit Owner"
    And I fill the field named "telephone" with value "nonnumeric"
    And I click on the button with text "Update Owner"
    Then I should see the "Owner" page
    And I should see the text "Telephone must be numeric, up to 10 digits"

  Scenario: TC_OWNER_009 Update owner with telephone number exceeding 10 digits
    Given I go to the main page
    When I click on the link with title "find owners"
    And I fill the field named "lastName" with value "Franklin"
    And I submit the form "search-owner-form"
    And I click on the link with text "Edit Owner"
    And I fill the field named "telephone" with value "11223344556"
    And I click on the button with text "Update Owner"
    Then I should see the "Owner" page
    And I should see the text "Telephone must be numeric, up to 10 digits"

