"""Tests for pkglink parsing functionality."""

from dataclasses import dataclass

import pytest

from pkglink.models import SourceSpec
from pkglink.parsing import build_uv_install_spec, parse_source


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
        result = parse_source(case.source)

        assert result.source_type == case.expected_type
        assert result.name == case.expected_name
        assert result.org == case.expected_org
        assert result.version == case.expected_version

    @pytest.mark.parametrize(
        'invalid_source',
        [
            '',
            'github:',
            'github:org/',
            'github:/repo',
        ],
    )
    def test_parse_source_invalid(self, invalid_source: str) -> None:
        """Test parsing invalid source specifications."""
        with pytest.raises(ValueError, match='Invalid source format'):
            parse_source(invalid_source)


class TestBuildUVInstallSpec:
    """Tests for build_uv_install_spec function."""

    @pytest.mark.parametrize(
        'case',
        [
            UVSpecTestCase(
                spec=SourceSpec(source_type='github', name='repo', org='org'),
                expected='git+https://github.com/org/repo.git',
            ),
            UVSpecTestCase(
                spec=SourceSpec(
                    source_type='github',
                    name='repo',
                    org='org',
                    version='v1.0',
                ),
                expected='git+https://github.com/org/repo.git@v1.0',
            ),
            UVSpecTestCase(
                spec=SourceSpec(source_type='package', name='mypackage'),
                expected='mypackage',
            ),
            UVSpecTestCase(
                spec=SourceSpec(
                    source_type='package',
                    name='mypackage',
                    version='1.0.0',
                ),
                expected='mypackage==1.0.0',
            ),
        ],
    )
    def test_build_uv_install_spec_valid(self, case: UVSpecTestCase) -> None:
        """Test building UV install specs for valid sources."""
        result = build_uv_install_spec(case.spec)
        assert result == case.expected

    def test_build_uv_install_spec_local_raises(self) -> None:
        """Test that local sources raise an error."""
        spec = SourceSpec(source_type='local', name='localpath')
        with pytest.raises(
            ValueError,
            match='Cannot build UV spec for local source',
        ):
            build_uv_install_spec(spec)
