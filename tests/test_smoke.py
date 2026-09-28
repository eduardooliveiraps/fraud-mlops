def test_package_imports():
    import fraud

    assert fraud.__name__ == "fraud"
