from cloudra.tools.name_hints import hint_unknown_tool


def test_retired_names_point_at_new_surface():
    assert "read" in hint_unknown_tool("text_reader")
    assert "read" in hint_unknown_tool("pdf2md")
    assert "search" in hint_unknown_tool("web_search")
    assert "source=" in hint_unknown_tool("paper_searcher")
    assert "bash" in hint_unknown_tool("bashtools")
    assert "write" in hint_unknown_tool("text_writer")
    assert "edit" in hint_unknown_tool("edit_file")
    assert "get_skill" in hint_unknown_tool("getskill")
    assert "browser" in hint_unknown_tool("web_fetcher")
    assert "browser" in hint_unknown_tool("web_fetch")
    assert "browser" in hint_unknown_tool("headless_browser")
    assert "subagent_launcher" in hint_unknown_tool("SubAgentLauncher")
    assert "subagent_swarm" in hint_unknown_tool("SubAgentSwarm")


def test_unknown_name_has_no_retired_mapping():
    msg = hint_unknown_tool("does_not_exist_xyz123")
    assert "does_not_exist_xyz123" in msg
    assert "read" not in msg.split("Did you mean")[0] if "Did you mean" in msg else True


def test_fuzzy_suggestion_for_misspelled_tool():
    msg = hint_unknown_tool("dag_propose", available_tools=["dag_propose_mechanism", "get_skill"])
    assert "Did you mean 'dag_propose_mechanism'?" in msg
