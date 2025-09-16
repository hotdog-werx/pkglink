"""Tests for pkglink main CLI functionality."""

import sys
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

import pkglink.main as main_module
from pkglink.main import (
    execute_symlink_operation,
    handle_dry_run,
)
from pkglink.main import (
    main as main_function,
)
from pkglink.models import CliArgs, LinkOperation, LinkTarget, SourceSpec


class TestHandleDryRun:
    """Tests for dry run functionality."""

    def test_handle_dry_run_when_dry_run_false(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Test that handle_dry_run does nothing when dry_run is False."""
        mock_logger = mocker.patch.object(main_module, 'logger')

        args = CliArgs(
            source='mypackage',
            directory='resources',
            dry_run=False,
            force=False,
            verbose=False,
        )
        install_spec = SourceSpec(source_type='package', name='mypackage')

        handle_dry_run(args, install_spec, 'mypackage')

        # Should not log anything
        mock_logger.info.assert_not_called()

    def test_handle_dry_run_when_dry_run_true(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Test that handle_dry_run logs when dry_run is True."""
        mock_logger = mocker.patch.object(main_module, 'logger')

        args = CliArgs(
            source='mypackage',
            directory='resources',
            dry_run=True,
            force=False,
            verbose=False,
            symlink_name='.custom',
        )
        install_spec = SourceSpec(source_type='package', name='mypackage')

        handle_dry_run(args, install_spec, 'mypackage')

        # Should log dry run information
        mock_logger.info.assert_called_once_with(
            'dry_run_mode',
            directory='resources',
            module_name='mypackage',
            symlink_name='.custom',
            _verbose_install_spec=install_spec.model_dump(),
        )

    def test_handle_dry_run_default_symlink_name(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Test that handle_dry_run uses default symlink name when not provided."""
        mock_logger = mocker.patch.object(main_module, 'logger')

        args = CliArgs(
            source='mypackage',
            directory='resources',
            dry_run=True,
            force=False,
            verbose=False,
            symlink_name=None,
        )
        install_spec = SourceSpec(source_type='package', name='mypackage')

        handle_dry_run(args, install_spec, 'mypackage')

        # Should use default symlink name
        mock_logger.info.assert_called_once_with(
            'dry_run_mode',
            directory='resources',
            module_name='mypackage',
            symlink_name='.mypackage',
            _verbose_install_spec=install_spec.model_dump(),
        )


class TestExecuteSymlinkOperation:
    """Tests for symlink operation execution."""

    def test_execute_symlink_operation_source_not_exists(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """Test error handling when source directory doesn't exist."""
        mock_logger = mocker.patch.object(main_module, 'logger')
        mock_stderr = mocker.patch.object(sys.stderr, 'write')

        non_existent_source = tmp_path / 'nonexistent'

        args = CliArgs(
            source='mypackage',
            directory='resources',
            dry_run=False,
            force=False,
            verbose=False,
        )

        operation = LinkOperation(
            spec=SourceSpec(source_type='package', name='mypackage'),
            target=LinkTarget(
                source_path=non_existent_source,
                target_directory='resources',
                symlink_name=None,
            ),
            force=False,
            dry_run=False,
        )

        with pytest.raises(SystemExit) as exc_info:
            execute_symlink_operation(args, operation)

        assert exc_info.value.code == 1
        mock_logger.error.assert_called_with(
            'source_directory_not_found',
            path=str(operation.full_source_path),
        )
        mock_stderr.assert_called()

    def test_execute_symlink_operation_success(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """Test successful symlink operation."""
        mocker.patch.object(main_module, 'logger')
        mock_create_symlink = mocker.patch.object(
            main_module,
            'create_symlink',
            return_value=True,
        )

        source_dir = tmp_path / 'source'
        source_dir.mkdir()
        # Create the target directory that the operation expects
        resources_dir = source_dir / 'resources'
        resources_dir.mkdir()

        args = CliArgs(
            source='mypackage',
            directory='resources',
            dry_run=False,
            force=False,
            verbose=False,
        )

        operation = LinkOperation(
            spec=SourceSpec(source_type='package', name='mypackage'),
            target=LinkTarget(
                source_path=source_dir,
                target_directory='resources',
                symlink_name=None,
            ),
            force=False,
            dry_run=False,
        )

        mocker.patch.object(main_module.Path, 'cwd', return_value=tmp_path)
        execute_symlink_operation(args, operation)

        mock_create_symlink.assert_called_once()


class TestMainFunction:
    """Tests for main CLI function."""

    def test_main_target_already_exists(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """Test main function when target exists but is not a symlink."""
        mocker.patch.object(main_module, 'configure_logging')
        mock_parse_args = mocker.patch.object(
            main_module,
            'parse_args_to_model',
        )
        mock_determine_spec = mocker.patch.object(
            main_module,
            'determine_install_spec_and_module',
        )
        mock_resolve_source = mocker.patch.object(
            main_module,
            'resolve_source_path',
        )
        mock_execute_operation = mocker.patch.object(
            main_module,
            'execute_symlink_operation',
        )

        # Mock parsed args
        args = CliArgs(
            source='mypackage',
            directory='resources',
            dry_run=False,
            force=False,
            verbose=False,
            symlink_name='.mylink',
        )
        mock_parse_args.return_value = args

        # Mock install spec
        install_spec = SourceSpec(source_type='package', name='mypackage')
        mock_determine_spec.return_value = (install_spec, 'mypackage')

        # Mock source resolution
        source_path = tmp_path / 'source'
        source_path.mkdir()
        (source_path / 'resources').mkdir()
        mock_resolve_source.return_value = source_path

        # Create existing target as directory (not symlink)
        existing_target = tmp_path / '.mylink'
        existing_target.mkdir()

        mocker.patch.object(main_module.Path, 'cwd', return_value=tmp_path)
        main_function()

        # Should proceed with execution since target is not a symlink
        mock_execute_operation.assert_called_once()

    def test_main_target_already_exists_and_correct(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """Test that main skips when target already exists and points to correct location."""
        mock_logger = mocker.patch.object(main_module, 'logger')
        mocker.patch.object(main_module, 'configure_logging')
        mock_parse_args = mocker.patch.object(
            main_module,
            'parse_args_to_model',
        )
        mock_determine_spec = mocker.patch.object(
            main_module,
            'determine_install_spec_and_module',
        )
        mock_resolve_source = mocker.patch.object(
            main_module,
            'resolve_source_path',
        )

        # Mock parsed args
        args = CliArgs(
            source='mypackage',
            directory='resources',
            dry_run=False,
            force=False,
            verbose=False,
            symlink_name='.mylink',
        )
        mock_parse_args.return_value = args

        # Mock install spec
        install_spec = SourceSpec(source_type='package', name='mypackage')
        mock_determine_spec.return_value = (install_spec, 'mypackage')

        # Create source path and mock resolution
        source_path = tmp_path / 'source'
        source_path.mkdir()
        (source_path / 'resources').mkdir()
        mock_resolve_source.return_value = source_path

        # Create existing symlink pointing to correct location
        existing_target = tmp_path / 'current' / '.mylink'
        existing_target.parent.mkdir()
        existing_target.symlink_to(
            source_path / 'resources',
            target_is_directory=True,
        )

        mocker.patch.object(
            main_module.Path,
            'cwd',
            return_value=tmp_path / 'current',
        )
        main_function()

        mock_logger.info.assert_any_call(
            'target_already_exists_and_correct_skipping',
            target=str(existing_target),
            symlink_name='.mylink',
        )

    def test_main_target_exists_but_wrong_location(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """Test that main updates symlink when it points to wrong location."""
        mocker.patch.object(main_module, 'configure_logging')
        mock_parse_args = mocker.patch.object(
            main_module,
            'parse_args_to_model',
        )
        mock_determine_spec = mocker.patch.object(
            main_module,
            'determine_install_spec_and_module',
        )
        mock_resolve_source = mocker.patch.object(
            main_module,
            'resolve_source_path',
        )
        mock_execute_operation = mocker.patch.object(
            main_module,
            'execute_symlink_operation',
        )

        # Mock parsed args
        args = CliArgs(
            source='mypackage',
            directory='resources',
            dry_run=False,
            force=False,
            verbose=False,
            symlink_name='.mylink',
        )
        mock_parse_args.return_value = args

        # Mock install spec
        install_spec = SourceSpec(source_type='package', name='mypackage')
        mock_determine_spec.return_value = (install_spec, 'mypackage')

        # Create source paths
        correct_source = tmp_path / 'correct_source'
        correct_source.mkdir()
        (correct_source / 'resources').mkdir()

        wrong_source = tmp_path / 'wrong_source'
        wrong_source.mkdir()
        (wrong_source / 'resources').mkdir()

        mock_resolve_source.return_value = correct_source

        # Create existing symlink pointing to wrong location
        current_dir = tmp_path / 'current'
        current_dir.mkdir()
        existing_target = current_dir / '.mylink'
        existing_target.symlink_to(
            wrong_source / 'resources',
            target_is_directory=True,
        )

        mocker.patch.object(main_module.Path, 'cwd', return_value=current_dir)
        main_function()

        # Should proceed with execution since symlink points to wrong location
        mock_execute_operation.assert_called_once()

    def test_main_dry_run_mode(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """Test main function in dry run mode."""
        mocker.patch.object(main_module, 'configure_logging')
        mocker.patch.object(main_module, 'logger')
        mock_parse_args = mocker.patch.object(
            main_module,
            'parse_args_to_model',
        )
        mock_determine_spec = mocker.patch.object(
            main_module,
            'determine_install_spec_and_module',
        )
        mock_handle_dry_run = mocker.patch.object(main_module, 'handle_dry_run')

        # Mock parsed args
        args = CliArgs(
            source='mypackage',
            directory='resources',
            dry_run=True,
            force=False,
            verbose=True,
            symlink_name=None,
        )
        mock_parse_args.return_value = args

        # Mock install spec
        install_spec = SourceSpec(source_type='package', name='mypackage')
        mock_determine_spec.return_value = (install_spec, 'mypackage')

        mocker.patch.object(main_module.Path, 'cwd', return_value=tmp_path)
        main_function()

        mock_handle_dry_run.assert_called_once_with(
            args,
            install_spec,
            'mypackage',
        )

    def test_main_successful_execution(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """Test successful main function execution."""
        mocker.patch.object(main_module, 'configure_logging')
        mocker.patch.object(main_module, 'logger')
        mock_parse_args = mocker.patch.object(
            main_module,
            'parse_args_to_model',
        )
        mock_determine_spec = mocker.patch.object(
            main_module,
            'determine_install_spec_and_module',
        )
        mock_resolve_source = mocker.patch.object(
            main_module,
            'resolve_source_path',
        )
        mock_execute_operation = mocker.patch.object(
            main_module,
            'execute_symlink_operation',
        )

        # Mock parsed args
        args = CliArgs(
            source='mypackage',
            directory='resources',
            dry_run=False,
            force=False,
            verbose=False,
            symlink_name='.mylink',
        )
        mock_parse_args.return_value = args

        # Mock install spec and resolved path
        install_spec = SourceSpec(source_type='package', name='mypackage')
        mock_determine_spec.return_value = (install_spec, 'mypackage')

        resolved_path = tmp_path / 'fake' / 'resolved' / 'path'
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_path.mkdir()
        mock_resolve_source.return_value = resolved_path

        mocker.patch.object(main_module.Path, 'cwd', return_value=tmp_path)
        main_function()

        mock_resolve_source.assert_called_once_with(install_spec, 'mypackage')
        mock_execute_operation.assert_called_once()

    def test_main_exception_handling(self, mocker: MockerFixture) -> None:
        """Test main function exception handling."""
        mocker.patch.object(main_module, 'configure_logging')
        mock_logger = mocker.patch.object(main_module, 'logger')
        mock_parse_args = mocker.patch.object(
            main_module,
            'parse_args_to_model',
        )
        mock_stderr = mocker.patch.object(sys.stderr, 'write')

        # Mock to raise exception
        mock_parse_args.side_effect = RuntimeError('Test error')

        with pytest.raises(SystemExit) as exc_info:
            main_function()

        assert exc_info.value.code == 1
        mock_logger.exception.assert_called_once_with(
            'cli_operation_failed',
            error='Test error',
        )
        mock_stderr.assert_called_once_with('Error: Test error\n')

    def test_main_with_force_overwrite(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """Test main function with force overwrite of existing target."""
        mocker.patch.object(main_module, 'configure_logging')
        mock_logger = mocker.patch.object(main_module, 'logger')
        mock_parse_args = mocker.patch.object(
            main_module,
            'parse_args_to_model',
        )
        mock_determine_spec = mocker.patch.object(
            main_module,
            'determine_install_spec_and_module',
        )
        mock_resolve_source = mocker.patch.object(
            main_module,
            'resolve_source_path',
        )
        mock_execute_operation = mocker.patch.object(
            main_module,
            'execute_symlink_operation',
        )

        # Mock parsed args with force=True
        args = CliArgs(
            source='mypackage',
            directory='resources',
            dry_run=False,
            force=True,
            verbose=False,
            symlink_name='.mylink',
        )
        mock_parse_args.return_value = args

        # Mock install spec
        install_spec = SourceSpec(source_type='package', name='mypackage')
        mock_determine_spec.return_value = (install_spec, 'mypackage')

        resolved_path = tmp_path / 'fake' / 'resolved' / 'path'
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_path.mkdir()

        mock_resolve_source.return_value = resolved_path

        # Create existing target
        existing_target = tmp_path / '.mylink'
        existing_target.mkdir()

        mocker.patch.object(main_module.Path, 'cwd', return_value=tmp_path)
        main_function()

        # Should proceed with execution despite existing target because force=True
        mock_resolve_source.assert_called_once_with(install_spec, 'mypackage')
        mock_execute_operation.assert_called_once()

        # Should log the starting message
        mock_logger.info.assert_any_call(
            'starting_pkglink',
            source='mypackage',
            directory='resources',
            dry_run=False,
            force=True,
            _verbose_args=args.model_dump(),
        )

    def test_main_target_already_exists_runs_post_install_setup(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """Test that main runs post-install setup even when target already exists and is correct."""
        mocker.patch.object(main_module, 'configure_logging')
        mock_parse_args = mocker.patch.object(
            main_module,
            'parse_args_to_model',
        )
        mock_determine_spec = mocker.patch.object(
            main_module,
            'determine_install_spec_and_module',
        )
        mock_resolve_source = mocker.patch.object(
            main_module,
            'resolve_source_path',
        )
        mock_run_post_install = mocker.patch.object(
            main_module,
            'run_post_install_setup',
        )

        # Mock parsed args (no_setup=False by default)
        args = CliArgs(
            source='mypackage',
            directory='resources',
            dry_run=False,
            force=False,
            verbose=False,
            symlink_name='.mylink',
            no_setup=False,
        )
        mock_parse_args.return_value = args

        # Mock install spec
        install_spec = SourceSpec(source_type='package', name='mypackage')
        mock_determine_spec.return_value = (install_spec, 'mypackage')

        # Create source path and mock resolution
        source_path = tmp_path / 'source'
        source_path.mkdir()
        (source_path / 'resources').mkdir()
        mock_resolve_source.return_value = source_path

        # Create existing symlink pointing to correct location
        existing_target = tmp_path / 'current' / '.mylink'
        existing_target.parent.mkdir()
        existing_target.symlink_to(
            source_path / 'resources',
            target_is_directory=True,
        )

        mocker.patch.object(
            main_module.Path,
            'cwd',
            return_value=tmp_path / 'current',
        )
        main_function()

        # Verify post-install setup was called
        mock_run_post_install.assert_called_once_with(
            linked_path=existing_target,
            base_dir=existing_target.parent,
        )

    def test_main_target_already_exists_skips_post_install_setup_when_disabled(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """Test that main skips post-install setup when --no-setup is used."""
        mocker.patch.object(main_module, 'configure_logging')
        mock_parse_args = mocker.patch.object(
            main_module,
            'parse_args_to_model',
        )
        mock_determine_spec = mocker.patch.object(
            main_module,
            'determine_install_spec_and_module',
        )
        mock_resolve_source = mocker.patch.object(
            main_module,
            'resolve_source_path',
        )
        mock_run_post_install = mocker.patch.object(
            main_module,
            'run_post_install_setup',
        )

        # Mock parsed args with no_setup=True
        args = CliArgs(
            source='mypackage',
            directory='resources',
            dry_run=False,
            force=False,
            verbose=False,
            symlink_name='.mylink',
            no_setup=True,
        )
        mock_parse_args.return_value = args

        # Mock install spec
        install_spec = SourceSpec(source_type='package', name='mypackage')
        mock_determine_spec.return_value = (install_spec, 'mypackage')

        # Create source path and mock resolution
        source_path = tmp_path / 'source'
        source_path.mkdir()
        (source_path / 'resources').mkdir()
        mock_resolve_source.return_value = source_path

        # Create existing symlink pointing to correct location
        existing_target = tmp_path / 'current' / '.mylink'
        existing_target.parent.mkdir()
        existing_target.symlink_to(
            source_path / 'resources',
            target_is_directory=True,
        )

        mocker.patch.object(
            main_module.Path,
            'cwd',
            return_value=tmp_path / 'current',
        )
        main_function()

        # Verify post-install setup was NOT called
        mock_run_post_install.assert_not_called()
