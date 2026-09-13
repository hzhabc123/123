# engine/engine.py

from abc import ABC, abstractmethod


class Engine(ABC):

    @abstractmethod
    def run(self):
        pass