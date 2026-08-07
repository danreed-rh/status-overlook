from status_overlook.jira_ids import is_jira_key, qa_field_to_jql, safe_jql_status


def test_is_jira_key():
    assert is_jira_key("RHOAIENG-81030")
    assert is_jira_key("X-1")
    assert not is_jira_key("")
    assert not is_jira_key("rhoaieng-1")
    assert not is_jira_key("RHOAIENG-81030 OR key = HACK")
    assert not is_jira_key("../etc")


def test_qa_field_to_jql():
    assert qa_field_to_jql("customfield_10470") == "cf[10470]"
    assert qa_field_to_jql("customfield_1") == "cf[1]"
    assert qa_field_to_jql("summary") is None
    assert qa_field_to_jql("customfield_x") is None
    assert qa_field_to_jql("") is None


def test_safe_jql_status():
    assert safe_jql_status("Testing") == "Testing"
    assert safe_jql_status('Te"sting') is None
    assert safe_jql_status("a\\b") is None
    assert safe_jql_status("") is None
