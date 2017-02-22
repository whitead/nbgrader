import os

import nbgrader


def test_nbextension():
    from nbgrader import _jupyter_nbextension_paths
    nbexts = _jupyter_nbextension_paths()
    assert len(nbexts) == 3
    assert nbexts[0]['section'] == 'tree'
    assert nbexts[1]['section'] == 'notebook'
    assert nbexts[2]['section'] == 'tree'
    paths = [ext['src'] for ext in nbexts]
    for path in paths:
        assert os.path.isdir(os.path.join(os.path.dirname(nbgrader.__file__), path))


def test_serverextension():
    from nbgrader import _jupyter_server_extension_paths
    serverexts = _jupyter_server_extension_paths()
    assert len(serverexts) == 2
    assert serverexts[0]['module'] == 'nbgrader.server_extensions.assignment_list'
    assert serverexts[1]['module'] == 'nbgrader.server_extensions.formgrader'
