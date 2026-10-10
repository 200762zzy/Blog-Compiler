from parser import parse_markdown


def test_empty_content_is_invalid():
    result = parse_markdown("   \n  ")
    assert result.is_valid is False
    assert result.error == "内容为空"
    assert result.images == []


def test_raw_markdown_is_preserved():
    content = "# 标题\n\n正文"
    assert parse_markdown(content).raw_markdown == content


def test_plain_markdown_is_valid():
    result = parse_markdown("# 标题\n\n一段正文。")
    assert result.is_valid is True
    assert result.error == ""


def test_extracts_image_paths_without_title():
    content = '![a](img/1.png)\n![b](img/2.png "标题")'
    assert parse_markdown(content).images == ["img/1.png", "img/2.png"]


def test_counts_fenced_code_blocks():
    content = "```python\nprint(1)\n```\n\n```js\nlet a = 1\n```"
    assert parse_markdown(content).code_block_count == 2


def test_odd_number_of_fences_floors_to_zero():
    content = "```python\nprint(1)\n"
    assert parse_markdown(content).code_block_count == 0


def test_blank_line_separated_paragraphs(): 
    content = "第一段\n\n第二段\n\n第三段"
    assert parse_markdown(content).paragraph_count == 3


def test_table_count_for_single_table():
    content = (
        "| 列A | 列B |\n"
        "| --- | --- |\n"
        "| 1 | 2 |\n"
        "| 3 | 4 |"
    )
    assert parse_markdown(content).table_count == 1


def test_table_count_for_two_tables():
    table = "| A | B |\n| --- | --- |\n| 1 | 2 |"
    content = table + "\n\n" + table
    assert parse_markdown(content).table_count == 2


def test_pipe_lines_without_separator_are_not_tables():
    content = "| 只是竖线 | 不是表格 |\n| 再来一行 | 依旧不是 |"
    assert parse_markdown(content).table_count == 0


def test_table_inside_code_block_is_ignored():
    content = "```\n| A | B |\n| --- | --- |\n| 1 | 2 |\n```"
    assert parse_markdown(content).table_count == 0


def test_headings_keep_level_and_text():
    content = "# 一级\n\n## 二级\n\n###### 六级"
    assert parse_markdown(content).headings == [
        (1, "一级"),
        (2, "二级"),
        (6, "六级"),
    ]


def test_hash_without_space_is_not_a_heading():
    assert parse_markdown("#藏在行内").headings == []


def test_combined_document_stats():
    content = (
        "# 标题\n\n"
        "正文一段。\n\n"
        "![截图](img/a.png)\n\n"
        "```py\nprint(1)\n```\n\n"
        "| A | B |\n| --- | --- |\n| 1 | 2 |"
    )
    result = parse_markdown(content)
    assert result.is_valid is True
    assert result.headings == [(1, "标题")]
    assert result.images == ["img/a.png"]
    assert result.code_block_count == 1
    assert result.paragraph_count == 5
    assert result.table_count == 1
