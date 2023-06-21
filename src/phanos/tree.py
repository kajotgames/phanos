from __future__ import annotations

import inspect
import typing


class MethodTree:
    """Class for storing order of method calls with its names"""

    parent: typing.Optional[MethodTree]
    children: typing.List[MethodTree]
    method: str

    def __init__(self, method: typing.Union[str, typing.Callable]) -> None:
        self.children = []
        if isinstance(method, str):
            self.method = method
        else:
            self.method = method.__name__
        self.parent = None

    # TODO: class name for all methods?
    def add_child(self, child: MethodTree) -> MethodTree:
        """Add child to method tree node
        :param child: child to be inserted
        """
        child.parent = self
        if self.method != "":
            class_name = self.get_class_name()
            if self.method.find(".") == -1 and self.method.find(":") == -1:
                self.method = class_name + ":" + self.method
            child.method = self.method + "." + child.method

        self.children.append(child)
        return child

    def delete_child(self) -> None:
        """Delete first child of node"""
        _ = self.children.pop(0)

    """    
    def print_postorder(self) -> None:
        '''print method names in postorder'''
        for child in self.children:
            child.print_postorder()
        if self.method != "":
            print(f"my method is {self.method}")
    """

    # TODO: check if its working
    @staticmethod
    def get_class_name() -> str:
        """get name of root class"""
        _stack = inspect.stack()
        # TODO: if not class -> module
        first_func = _stack[3]
        return first_func[0].f_locals["self"].__class__.__name__
