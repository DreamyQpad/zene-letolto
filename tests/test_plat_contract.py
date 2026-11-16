"""A két platformmodul közös felületének egyezése: ugyanazok a nevek, ugyanazok a kötelező paraméterek."""
import inspect
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import plat_linux  # noqa: E402
import plat_windows  # noqa: E402


def required_params(func):
    """A kötelező (alapértelmezés nélküli) paraméterek nevei; az opcionális extrák platformfüggők lehetnek."""
    return [name for name, p in inspect.signature(func).parameters.items() if p.default is p.empty]


class PlatContractTest(unittest.TestCase):
    def test_az_exportalt_nevek_egyeznek(self):
        self.assertEqual(set(plat_windows.__all__), set(plat_linux.__all__))

    def test_minden_nev_megvan_mindket_modulban(self):
        for module in (plat_windows, plat_linux):
            for name in module.__all__:
                with self.subTest(module=module.__name__, name=name):
                    self.assertTrue(hasattr(module, name))

    def test_a_hivhatok_kotelezo_parameterei_egyeznek(self):
        for name in plat_windows.__all__:
            win, lin = getattr(plat_windows, name), getattr(plat_linux, name)
            self.assertEqual(callable(win), callable(lin), name)
            if callable(win):
                with self.subTest(name=name):
                    self.assertEqual(required_params(win), required_params(lin))


if __name__ == "__main__":
    unittest.main()
