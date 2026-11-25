Feature: Owner Validation

  Scenario: TC_OWNER_001 Display of telephone field hint message on Add New Owner page
    Given I go to the main page
    When I click on the link with title "find owners"
    And I click on the link with text "Add Owner"
    Then I should see the text "All fields are required. Telephone must be numeric, up to 10 digits."

  Scenario: TC_OWNER_002 Create owner with a valid 10-digit numeric telephone
    Given I go to the main page
    When I click on the link with title "find owners"
    And I click on the link with text "Add Owner"
    And I fill the field named "firstName" with value "Test"
    And I fill the field named "lastName" with value "Owner"
    And I fill the field named "address" with value "123 Test St"
    And I fill the field named "city" with value "Testville"
    And I fill the field named "telephone" with value "1234567890"
    And I click on the button with text "Add Owner"
    Then I should see the "Owner Information" page
    And I should see the text "Test Owner"
    And I should see the text "1234567890"

  Scenario: TC_OWNER_003 Create owner with a valid numeric telephone (less than 10 digits)
    Given I go to the main page
    When I click on the link with title "find owners"
    And I click on the link with text "Add Owner"
    And I fill the field named "firstName" with value "Short"
    And I fill the field named "lastName" with value "Number"
    And I fill the field named "address" with value "456 Short Ave"
    And I fill the field named "city" with value "Shortville"
    And I fill the field named "telephone" with value "12345"
    And I click on the button with text "Add Owner"
    Then I should see the "Owner Information" page
    And I should see the text "Short Number"
    And I should see the text "12345"

  Scenario: TC_OWNER_004 Attempt to create owner with non-numeric telephone
    Given I go to the main page
    When I click on the link with title "find owners"
    And I click on the link with text "Add Owner"
    And I fill the field named "firstName" with value "Invalid"
    And I fill the field named "lastName" with value "Phone"
    And I fill the field named "address" with value "789 Invalid Rd"
    And I fill the field named "city" with value "Invalidtown"
    And I fill the field named "telephone" with value "abcde"
    And I click on the button with text "Add Owner"
    Then I should see the text "Telephone must be numeric, up to 10 digits"
    And I should not see the text "Invalid Phone"

  Scenario: TC_OWNER_005 Attempt to create owner with telephone exceeding 10 digits
    Given I go to the main page
    When I click on the link with title "find owners"
    And I click on the link with text "Add Owner"
    And I fill the field named "firstName" with value "Long"
    And I fill the field named "lastName" with value "Number"
    And I fill the field named "address" with value "101 Long St"
    And I fill the field named "city" with value "Longville"
    And I fill the field named "telephone" with value "12345678901"
    And I click on the button with text "Add Owner"
    Then I should see the text "Telephone must be numeric, up to 10 digits"
    And I should not see the text "Long Number"

  Scenario: TC_OWNER_006 Attempt to create owner with empty telephone
    Given I go to the main page
    When I click on the link with title "find owners"
    And I click on the link with text "Add Owner"
    And I fill the field named "firstName" with value "Empty"
    And I fill the field named "lastName" with value "Phone"
    And I fill the field named "address" with value "202 Empty St"
    And I fill the field named "city" with value "Emptyville"
    And I click on the button with text "Add Owner"
    Then I should see the text "may not be empty"
    And I should not see the text "Empty Phone"

  Scenario: TC_OWNER_007 Update owner with a valid 10-digit numeric telephone
    Given I go to the main page
    When I click on the link with title "find owners"
    And I fill the field named "lastName" with value "Franklin"
    And I submit the form "search-owner-form"
    And I click on the link with text "Edit Owner"
    And I fill the field named "telephone" with value "9876543210"
    And I click on the button with text "Update Owner"
    Then I should see the "Owner Information" page
    And I should see the text "George Franklin"
    And I should see the text "9876543210"

  Scenario: TC_OWNER_008 Attempt to update owner with non-numeric telephone
    Given I go to the main page
    When I click on the link with title "find owners"
    And I fill the field named "lastName" with value "Franklin"
    And I submit the form "search-owner-form"
    And I click on the link with text "Edit Owner"
    And I fill the field named "telephone" with value "invalid"
    And I click on the button with text "Update Owner"
    Then I should see the text "Telephone must be numeric, up to 10 digits"
    And I should see the text "George Franklin"

  Scenario: TC_OWNER_009 Attempt to update owner with telephone exceeding 10 digits
    Given I go to the main page
    When I click on the link with title "find owners"
    And I fill the field named "lastName" with value "Franklin"
    And I submit the form "search-owner-form"
    And I click on the link with text "Edit Owner"
    And I fill the field named "telephone" with value "11223344556"
    And I click on the button with text "Update Owner"
    Then I should see the text "Telephone must be numeric, up to 10 digits"
    And I should see the text "George Franklin"

  Scenario: TC_OWNER_010 Attempt to update owner with empty telephone
    Given I go to the main page
    When I click on the link with title "find owners"
    And I fill the field named "lastName" with value "Franklin"
    And I submit the form "search-owner-form"
    And I click on the link with text "Edit Owner"
    And I clear the field named "telephone"
    And I click on the button with text "Update Owner"
    Then I should see the text "may not be empty"
    And I should see the text "George Franklin"
