"""Fondant pipelines test."""
import copy
from pathlib import Path

import pytest
import yaml
from fondant.exceptions import InvalidPipelineDefinition, InvalidTypeSchema
from fondant.pipeline import ComponentOp, Pipeline

valid_pipeline_path = Path(__file__).parent / "example_pipelines/valid_pipeline"
invalid_pipeline_path = Path(__file__).parent / "example_pipelines/invalid_pipeline"


def yaml_file_to_dict(file_path):
    with open(file_path) as file:
        return yaml.safe_load(file)


@pytest.fixture()
def default_pipeline_args():
    return {
        "pipeline_name": "pipeline",
        "base_path": "gs://bucket/blob",
    }


@pytest.fixture()
def mocked_component_op(monkeypatch):
    # Define the mock method
    def mocked_get_component_cache_key(self):
        return "42"

    # Apply the monkeypatch to replace the original method with the mocked method
    monkeypatch.setattr(
        ComponentOp,
        "get_component_cache_key",
        mocked_get_component_cache_key,
    )

    # Return a function that takes custom arguments and returns an instance of ComponentOp
    def create_mocked_component_op(component_dir, **kwargs):
        return ComponentOp(component_dir=component_dir, **kwargs)

    return create_mocked_component_op


@pytest.mark.parametrize(
    "valid_pipeline_example",
    [
        (
            "example_1",
            ["first_component", "second_component", "third_component"],
        ),
    ],
)
def test_component_op(
    valid_pipeline_example,
    mocked_component_op,
):
    component_args = {"storage_args": "a dummy string arg"}
    example_dir, component_names = valid_pipeline_example
    components_path = Path(valid_pipeline_path / example_dir)

    mocked_component_op(
        Path(components_path / component_names[0]),
        arguments=component_args,
        output_partition_size=None,
    )

    mocked_component_op(
        Path(components_path / component_names[0]),
        arguments=component_args,
        output_partition_size="250MB",
    )

    with pytest.raises(InvalidTypeSchema):
        mocked_component_op(
            Path(components_path / component_names[0]),
            arguments=component_args,
            output_partition_size="10",
        )

    with pytest.raises(InvalidTypeSchema):
        mocked_component_op(
            Path(components_path / component_names[0]),
            arguments=component_args,
            output_partition_size="250 MB",
        )


@pytest.mark.parametrize(
    "valid_pipeline_example",
    [
        (
            "example_1",
            ["first_component", "second_component", "third_component"],
        ),
    ],
)
def test_component_op_hash(
    valid_pipeline_example,
    monkeypatch,
):
    example_dir, component_names = valid_pipeline_example
    components_path = Path(valid_pipeline_path / example_dir)

    comp_0_op_spec_0 = ComponentOp(
        Path(components_path / component_names[0]),
        arguments={"storage_args": "a dummy string arg"},
        output_partition_size=None,
    )

    comp_0_op_spec_1 = ComponentOp(
        Path(components_path / component_names[0]),
        arguments={"storage_args": "a different string arg"},
        output_partition_size=None,
    )

    comp_1_op_spec_0 = ComponentOp(
        Path(components_path / component_names[1]),
        arguments={"storage_args": "a dummy string arg"},
        output_partition_size=None,
    )

    monkeypatch.setattr(
        comp_0_op_spec_0,
        "get_component_image_hash",
        lambda self: "1234",
    )
    monkeypatch.setattr(
        comp_0_op_spec_1,
        "get_component_image_hash",
        lambda self: "1234",
    )
    monkeypatch.setattr(
        comp_1_op_spec_0,
        "get_component_image_hash",
        lambda self: "1234",
    )

    comp_0_op_spec_0_copy = copy.deepcopy(comp_0_op_spec_0)

    assert (
        comp_0_op_spec_0.get_component_cache_key()
        != comp_0_op_spec_1.get_component_cache_key()
    )
    assert (
        comp_0_op_spec_0.get_component_cache_key()
        == comp_0_op_spec_0_copy.get_component_cache_key()
    )
    assert (
        comp_0_op_spec_0.get_component_cache_key()
        != comp_1_op_spec_0.get_component_cache_key()
    )

    monkeypatch.setattr(
        comp_0_op_spec_0_copy,
        "get_component_image_hash",
        lambda self: "5678",
    )

    assert (
        comp_0_op_spec_0.get_component_cache_key()
        != comp_0_op_spec_0_copy.get_component_cache_key()
    )


@pytest.mark.parametrize(
    "valid_pipeline_example",
    [
        (
            "example_1",
            ["first_component", "second_component", "third_component"],
        ),
    ],
)
def test_valid_pipeline(
    default_pipeline_args,
    mocked_component_op,
    valid_pipeline_example,
    tmp_path,
    monkeypatch,
):
    """Test that a valid pipeline definition can be compiled without errors."""
    example_dir, component_names = valid_pipeline_example
    component_args = {"storage_args": "a dummy string arg"}
    components_path = Path(valid_pipeline_path / example_dir)

    pipeline = Pipeline(**default_pipeline_args)

    # override the default package_path with temporary path to avoid the creation of artifacts
    monkeypatch.setattr(pipeline, "package_path", str(tmp_path / "test_pipeline.tgz"))

    first_component_op = mocked_component_op(
        Path(components_path / component_names[0]),
        arguments=component_args,
    )
    second_component_op = mocked_component_op(
        Path(components_path / component_names[1]),
        arguments=component_args,
    )
    third_component_op = mocked_component_op(
        Path(components_path / component_names[2]),
        arguments=component_args,
    )

    pipeline.add_op(third_component_op, dependencies=second_component_op)
    pipeline.add_op(first_component_op)
    pipeline.add_op(second_component_op, dependencies=first_component_op)

    pipeline.sort_graph()
    assert list(pipeline._graph.keys()) == [
        "First component",
        "Second component",
        "Third component",
    ]
    assert pipeline._graph["First component"]["dependencies"] == []
    assert pipeline._graph["Second component"]["dependencies"] == ["First component"]
    assert pipeline._graph["Third component"]["dependencies"] == ["Second component"]

    pipeline.compile(cache_disabled=True)


@pytest.mark.parametrize(
    "valid_pipeline_example",
    [
        (
            "example_1",
            ["first_component", "second_component", "third_component"],
        ),
    ],
)
def test_invalid_pipeline_dependencies(
    default_pipeline_args,
    mocked_component_op,
    valid_pipeline_example,
    tmp_path,
    monkeypatch,
):
    """
    Test that an InvalidPipelineDefinition exception is raised when attempting to create a pipeline
    with more than one operation defined without dependencies.
    """
    example_dir, component_names = valid_pipeline_example
    components_path = Path(valid_pipeline_path / example_dir)
    component_args = {"storage_args": "a dummy string arg"}

    pipeline = Pipeline(**default_pipeline_args)

    first_component_op = mocked_component_op(
        Path(components_path / component_names[0]),
        arguments=component_args,
    )
    second_component_op = mocked_component_op(
        Path(components_path / component_names[1]),
        arguments=component_args,
    )
    third_component_op = mocked_component_op(
        Path(components_path / component_names[2]),
        arguments=component_args,
    )

    pipeline.add_op(third_component_op, dependencies=second_component_op)
    pipeline.add_op(second_component_op)
    with pytest.raises(InvalidPipelineDefinition):
        pipeline.add_op(first_component_op)


@pytest.mark.parametrize(
    "invalid_pipeline_example",
    [
        ("example_1", ["first_component", "second_component"]),
        ("example_2", ["first_component", "second_component"]),
    ],
)
def test_invalid_pipeline_compilation(
    default_pipeline_args,
    mocked_component_op,
    invalid_pipeline_example,
    tmp_path,
):
    """
    Test that an InvalidPipelineDefinition exception is raised when attempting to compile
    an invalid pipeline definition.
    """
    example_dir, component_names = invalid_pipeline_example
    components_path = Path(invalid_pipeline_path / example_dir)
    component_args = {"storage_args": "a dummy string arg"}

    pipeline = Pipeline(**default_pipeline_args)

    first_component_op = mocked_component_op(
        Path(components_path / component_names[0]),
        arguments=component_args,
    )
    second_component_op = mocked_component_op(
        Path(components_path / component_names[1]),
        arguments=component_args,
    )

    pipeline.add_op(first_component_op)
    pipeline.add_op(second_component_op, dependencies=first_component_op)

    with pytest.raises(InvalidPipelineDefinition):
        pipeline.compile(cache_disabled=True)


@pytest.mark.parametrize(
    "invalid_component_args",
    [
        {"invalid_arg": "a dummy string arg", "storage_args": "a dummy string arg"},
        {"args": 1, "storage_args": "a dummy string arg"},
    ],
)
def test_invalid_argument(
    default_pipeline_args,
    mocked_component_op,
    invalid_component_args,
    tmp_path,
):
    """
    Test that an exception is raised when the passed invalid argument name or type to the fondant
    component does not match the ones specified in the fondant specifications.
    """
    component_operation = mocked_component_op(
        valid_pipeline_path / "example_1" / "first_component",
        arguments=invalid_component_args,
    )

    pipeline = Pipeline(**default_pipeline_args)

    pipeline.add_op(component_operation)

    with pytest.raises((ValueError, TypeError)):
        pipeline.compile(cache_disabled=True)


def test_reusable_component_op():
    laion_retrieval_op = ComponentOp.from_registry(
        name="prompt_based_laion_retrieval",
        arguments={"num_images": 2, "aesthetic_score": 9, "aesthetic_weight": 0.5},
    )
    assert laion_retrieval_op.component_spec, "component_spec_path could not be loaded"

    component_name = "this_component_does_not_exist"
    with pytest.raises(
        ValueError,
        match=f"No reusable component with name {component_name} " "found.",
    ):
        ComponentOp.from_registry(
            name=component_name,
        )


def test_defining_reusable_component_op_with_custom_spec():
    load_from_hub_default_op = ComponentOp.from_registry(
        name="load_from_hf_hub",
        arguments={
            "dataset_name": "test_dataset",
            "column_name_mapping": {"foo": "bar"},
            "image_column_names": None,
        },
    )

    load_from_hub_custom_op = ComponentOp(
        load_from_hub_default_op.component_dir,
        arguments={
            "dataset_name": "test_dataset",
            "column_name_mapping": {"foo": "bar"},
            "image_column_names": None,
        },
    )

    assert (
        load_from_hub_custom_op.component_spec
        == load_from_hub_default_op.component_spec
    )


def test_pipeline_name():
    Pipeline(pipeline_name="valid-name", base_path="base_path")
    with pytest.raises(InvalidPipelineDefinition, match="The pipeline name violates"):
        Pipeline(pipeline_name="invalid name", base_path="base_path")
