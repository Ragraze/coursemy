from xml.etree import ElementTree

from app.routers.pages import templates


def render(value):
    return str(templates.env.get_template("partials/course_text.html").module.course_text(value))


def test_course_text_keeps_paragraphs_and_groups_explicit_lists():
    root = ElementTree.fromstring(render("Introduction.\n\nProjects:\n1.\u00a0First project\n2. Second project\nNotes:\n• A computer\n- Internet access\nFinal paragraph."))
    assert [element.tag for element in root] == ["p", "h3", "ol", "h3", "ul", "p"]
    assert [element.text for element in root.findall("p")] == ["Introduction.", "Final paragraph."]
    assert [element.text for element in root.findall("ol/li")] == ["First project", "Second project"]
    assert [element.text for element in root.findall("ul/li")] == ["A computer", "Internet access"]


def test_numbered_lists_keep_source_numbering():
    root = ElementTree.fromstring(render("3. Third\n4. Fourth\n8) Eighth"))
    assert [(element.attrib["start"], [item.text for item in element]) for element in root] == [
        ("3", ["Third", "Fourth"]), ("8", ["Eighth"]),
    ]
    assert len(ElementTree.fromstring(render(None))) == 0


def test_course_text_escapes_source_html():
    html = render('Details:\n- <script>alert(1)</script>\n1. <img src=x onerror=alert(1)>')
    assert "<script>" not in html
    assert "<img " not in html
    assert "&lt;script&gt;" in html
    assert '<ol class="detail-list" start="1">' in html
    assert '<ul class="detail-list">' in html
