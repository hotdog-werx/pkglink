"""Tests for pkglink parsing functionality."""

from dataclasses import dataclass

import pytest

from pkglink.argparse import argparse_source
from pkglink.models import SourceSpec


@dataclass
class ParseTestCase:
    """Test case for source parsing."""

    source: str
    expected_type: str
    expected_name: str
    expected_org: str | None = None
    expected_version: str | None = None


@dataclass
class UVSpecTestCase:
    """Test case for UV spec building."""

    spec: SourceSpec
    expected: str


class TestParseSource:
    """Tests for parse_source function."""

    @pytest.mark.parametrize(
        'case',
        [
            ParseTestCase(
                source='github:myorg/myrepo',
                expected_type='github',
                expected_name='myrepo',
                expected_org='myorg',
            ),
            ParseTestCase(
                source='github:myorg/myrepo@v1.0.0',
                expected_type='github',
                expected_name='myrepo',
                expected_org='myorg',
                expected_version='v1.0.0',
            ),
            ParseTestCase(
                source='./local/path',
                expected_type='local',
                expected_name='path',
            ),
            ParseTestCase(
                source='/absolute/path',
                expected_type='local',
                expected_name='path',
            ),
            ParseTestCase(
                source='~/home/path',
                expected_type='local',
                expected_name='path',
            ),
            ParseTestCase(
                source='C:\\\\Users\\\\test\\\\fake_toolbelt',
                expected_type='local',
                expected_name='fake_toolbelt',
            ),
            ParseTestCase(
                source='mypackage',
                expected_type='package',
                expected_name='mypackage',
            ),
            ParseTestCase(
                source='mypackage@1.0.0',
                expected_type='package',
                expected_name='mypackage',
                expected_version='1.0.0',
            ),
        ],
    )
    def test_parse_source_valid(self, case: ParseTestCase) -> None:
        """Test parsing valid source specifications."""
        result = argparse_source(case.source)

        assert result.source_type == case.expected_type
        assert result.name == case.expected_name
        assert result.org == case.expected_org
        assert result.version == case.expected_version
