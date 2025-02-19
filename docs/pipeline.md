# Pipeline 

A Fondant pipeline is a tool for building complex workflows by creating a Directed Acyclic Graph (DAG) of different components that need to be executed. With Fondant, you can use both reusable components and custom components to construct your pipeline. In order to build a pipeline you register components on it with dependencies (if any) and Fondant will construct the graph automatically.

## Composing a pipeline 

To build a pipeline, you need to define a set of component operations called `ComponentOp`. A component operation encapsulates the specifications of the component and its runtime configuration.

The component specifications include the location of the Docker image in a registry.

The runtime configuration consists of the component's arguments and the definition of node pools, resources and custom partitioning specification. For example, if a component requires GPU for model inference, you can specify the necessary GPU resources in the runtime configuration.

Here is an example of how to build a pipeline using Fondant:
```python
from fondant.pipeline import ComponentOp, Pipeline, Client

def build_pipeline():
    pipeline = Pipeline(pipeline_name="example pipeline", base_path="fs://bucket")

    load_from_hub_op = ComponentOp.from_registry(
        name="load_from_hf_hub",
        arguments={"dataset_name": "lambdalabs/pokemon-blip-captions"},
    )
    pipeline.add_op(load_from_hub_op)

    caption_images_op = ComponentOp(  
        component_dir="components/captioning_component",  
        arguments={  
            "model_id": "Salesforce/blip-image-captioning-base",  
            "batch_size": 2,  
            "max_new_tokens": 50,  
        },  
        number_of_gpus=1,
        node_pool_label="node_pool",  
        node_pool_name="model-inference-pool",  
    )
    pipeline.add_op(caption_images_op, dependencies=load_from_hub_op)
    return pipeline

```

In the example above, we first define our pipeline by providing a name as an identifier and a base path where the pipeline run artifacts will be stored. The base path can be a remote cloud location or a local directory, which is useful for local development.

Next, we define two operations: `load_from_hub_op`, which is a based from a reusable component loaded from the Fondant registry, and `caption_images_op`, which is a custom component defined by you. We add these components to the pipeline using the `.add_op()` method and specify the dependencies between components to build the DAG.


!!! note "IMPORTANT"
    Currently Fondant supports linear DAGs with single dependencies. Support for non-linear DAGs will be available in future releases.

## Setting Custom node pool parameters
Each component can optionally be constrained to run on particular node(s) using `node_pool_label` and `node_pool_name`. You can find these under the Kubernetes labels of your cluster. You can use the default node label provided by Kubernetes or attach your own. Note that the value of these labels is cloud provider specific.

## Setting Custom partitioning parameters

When working with Fondant, each component deals with datasets, and Dask is used internally 
to handle datasets larger than the available memory. To achieve this, the data is divided 
into smaller chunks called "partitions" that can be processed in parallel. Ensuring a sufficient number of partitions
enables parallel processing, where multiple workers process different partitions simultaneously, 
and smaller partitions ensure they fit into memory.

### How Fondant handles partitions

**1) Repartitioning the Loaded DataFrame:** This step is optional and comes into play if the number
of partitions is fewer than the available workers on the data processing instance.
By repartitioning, the maximum number of workers can be efficiently utilized, leading to faster
and parallel processing.

**2) Repartitioning the Written DataFrame:** The written dataframe is also repartitioned into
smaller sizes (default 250MB) to enable the next component to load these partitions into memory.


### Customizing Partitioning

By default, Fondant automatically handles the partitioning, but you can disable this and create your
own custom partitioning logic if you have specific requirements.

Here's an example of disabling the automatic partitioning:

```python

caption_images_op = ComponentOp(  
    component_dir="components/captioning_component",  
    arguments={  
        "model_id": "Salesforce/blip-image-captioning-base",  
        "batch_size": 2,  
        "max_new_tokens": 50,  
    },  
    input_partition_rows='disable',  
)
```

The code snippet above disables automatic partitions for both the loaded and written dataframes, 
allowing you to define your own partitioning logic inside the components.

Moreover, you have the flexibility to set your own custom partitioning parameters to override the default settings:

```python

caption_images_op = ComponentOp(  
    component_dir="components/captioning_component",  
    arguments={  
        "model_id": "Salesforce/blip-image-captioning-base",  
        "batch_size": 2,  
        "max_new_tokens": 50,  
    },  
    input_partition_rows=100, 
)
```

In the example above, each partition of the loaded dataframe will contain approximately one hundred rows,
and the size of the output partitions will be around 10MB. This capability is useful in scenarios
where processing one row significantly increases the number of rows in the dataset
(resulting in dataset explosion) or causes a substantial increase in row size (e.g., fetching images from URLs).  

By setting a lower value for input partition rows, you can mitigate issues where the processed data
grows larger than the available memory before being written to disk.

## Compiling and Running a pipeline

Once all your components are added to your pipeline you can use different compilers to run your pipeline:

!!! note "IMPORTANT"
  When using other runners you will need to make sure that your new environment has access to:
  - The base_path of your pipeline (can be storage bucket like S3, GCS, etc)
  - The images used in your pipeline (make sure you have access to the registries where the images are stored)

### Kubeflow

The Kubeflow compiler will take your pipeline and compile it to a Kubeflow pipeline spec. This spec can be used to run your pipeline on a Kubeflow cluster. There are 2 ways to compile your pipeline to a Kubeflow spec:

- Using the CLI:
```bash
fondant compile <pipeline_ref> --kubeflow --output <path_to_output>
```

- Using the compiler directly:
```python
from fondant.compiler import KubeFlowCompiler


pipeline = ...

compiler = KubeFlowCompiler()
compiler.compile(pipeline=pipeline, output_path="pipeline.yaml")
```

Both of these options will produce a kubeflow specification as a file, if you also want to immediately start a run you can also use the runner we provide (see below).

### Running a Kubeflow compiled pipeline

You will need a Kubeflow cluster to run your pipeline on and specify the host of that cluster. More info on setting up a Kubeflow pipelines deployment and the host path can be found in the [infrastructure documentation](infrastructure.md).

There are 2 ways to run a Kubeflow compiled pipeline:

- Using the CLI:
```bash
fondant run <pipeline_ref> --kubeflow --host <kubeflow_host>
```
NOTE: that the pipeline ref is the path to the compiled pipeline spec OR a reference to an fondant pipeline in which case the compiler will compile the pipeline first before running.


- Using the compiler directly:
```python
from fondant.compiler import KubeFlowCompiler
from fondant.runner import KubeflowRunner

# Your pipeline definition here

if __name__ == "__main__":
    compiler = KubeFlowCompiler()
    compiler.compile(pipeline=pipeline, output_path="pipeline.yaml")
    runner = KubeflowRunner(
        host="YOUR KUBEFLOW HOST",
    )
    runner.run(input_spec="pipeline.yaml")
```

Once your pipeline is running you can monitor it using the Kubeflow UI.

### Docker-Compose

This compiler and runner is mainly aimed at local development and quick iterations, there is no scaling so using small slices of your data is advised. 


The DockerCompiler will take your pipeline and create a docker-compose.yml file where every component is added as a service with the correct dependencies by leveraging the `depends_on` functionality and the `service_completed_successfully` status. See the basic example below:

```yaml
version: '3.8'
services:
  component_1:
    command: ["python", "main.py"]
    image: component_1:latest
  component_2:
    command: ["python", "main.py"]
    image: component_2:latest
    depends_on:
      component_1:
        condition: service_completed_successfully
  component_3:
    command: ["python", "main.py"]
    depends_on:
      component_2:
        condition: service_completed_successfully
    build: ./component_3
```

Note that for components that do not come from the registry (local custom components) the compiler will add a build subsection (see component_3 in the example above) instead of referring to the image specified in the `component_spec.yaml`. This allows docker-compose to build and rebuild the container used in that component allowing for quicker iteration.

In order to compile your pipeline to a `docker-compose` spec you need to import the `DockerCompiler`

```python
from fondant.compiler import DockerCompiler

compiler = DockerCompiler()
compiler.compile(pipeline=pipeline)
```

The DockerCompiler will try to see if the `base_path` of the pipeline is local or remote. If local the `base_path` will be mounted as a bind volume on every service/component.

If you want to use remote paths (GCS, S3, etc.) you can use the `extra_volumes` argument to mount extra credentials. This volume will be mounted to every component/service of the docker-compose spec.

```python
from fondant.compiler import DockerCompiler

extra_volumes = [
    # example for GCP, this mounts your application default credentials to the docker container
    "$HOME/.config/gcloud/application_default_credentials.json:/root/.config/gcloud/application_default_credentials.json:ro"
    # example for AWS, this mounts your current credentials to the docker container
    "$HOME/.aws/credentials:/root/.aws/credentials:ro"
]

compiler = DockerCompiler()
compiler.compile(pipeline=pipeline, extra_volumes=extra_volumes)
```

#### Running a Docker compiled pipeline

Navigate to the folder where your docker compose is located and run (you need to have a recent version of [docker-compose](https://docs.docker.com/compose/install/) installed)
```bash
docker compose up
```

Or you can use the fondant cli to run the pipeline:
```bash
fondant run <pipeline_ref> --local
```

NOTE: that the pipeline ref is the path to the compiled pipeline spec OR a reference to an fondant pipeline in which case the compiler will compile the pipeline first before running.

This will start the pipeline and provide logs per component(service).