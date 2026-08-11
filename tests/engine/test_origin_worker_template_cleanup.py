from __future__ import annotations

from plotagent.engine.backends.origin.worker import _install_template_workbook_guard


class _Book:
    def __init__(self, owner: _Origin, name: str) -> None:
        self.owner = owner
        self.name = name

    def destroy(self) -> None:
        self.owner.books.remove(self)


class _Origin:
    def __init__(self) -> None:
        self.books = [_Book(self, "Book1"), _Book(self, "Data")]
        self.new_graph = self._new_graph

    def pages(self, kind: str):
        assert kind == "w"
        return tuple(self.books)

    def _new_graph(self, *args: object, **kwargs: object) -> str:
        del args, kwargs
        self.books.append(_Book(self, "Book1"))
        return "Graph1"


def test_official_template_workbook_side_effect_is_removed_and_guard_restores() -> None:
    origin = _Origin()
    original = origin.new_graph
    restore = _install_template_workbook_guard(origin)

    assert origin.new_graph("Graph", template="LINE.otpu") == "Graph1"
    assert [book.name for book in origin.books] == ["Data"]

    restore()
    origin.new_graph("Graph", template="LINE.otpu")
    assert [book.name for book in origin.books] == ["Data", "Book1"]
    assert origin.new_graph == original
