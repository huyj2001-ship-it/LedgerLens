import ledgerlens
import ledgerlens_eval


def test_packages_import() -> None:
    assert ledgerlens.__version__
    assert ledgerlens_eval.__doc__
