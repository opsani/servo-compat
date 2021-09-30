# Compatibility Extensions for ServoX

Connectors for opsani/servox that provide functional compatibility with the older-generation 'opsani/servo' agent.

# Overview

These connectors extend ServoX with functionality functionality similar to and
compatible with with the legacy 'servo-k8senv' and 'servo-k8s' drivers for Opsani `servo`.

- `k8s_env`: Support for `{"control":{"environment":{"mode": X}}}` in describe/adjust/measure requests.
- `adjust_filter`: Support for `{"control":{"userdata":{"deploy_to": X}}}`

## `k8s_env`

This connector, when enabled and configured, installs a `before_event` handler for the describe, adjust and measure requests.
(NOTE: describe requests handling in ServoX currently ignores any 'control' data in the backend request, therefore 'describe' requests will never trigger the connector's operation)

If the request contains control data and has `{"environment":{"mode": X}}` in that data, the contents of a Kuberenetes deployment annotation defined in the configuration (`current_mode_...` settings) are examined. If the annotation value is the same as the value found in the control data, the `before_event` handler returns, allowing the request to proceed. Otherwise:

- the "mode" value from the control data is written as an annotation in the Kubernetes deployment designated for this in the configuration (`desired_mode_...` settings)
- processing of the request is stalled with 'sleep'. It is expected that the process will be restarted shortly after the 'desired mode' annotation is updated. If the sleep timeout expires, an exception is raised, causing the request to return as failed before it reaches any ServoX event handlers.

## `adjust_filter`

This connector, when enabled and configured, installs a `before_event` handler for the `adjust` requests. The requests are checked for the presence of `{"control":{"userdata":{"deploy_to": X}}}` and if it is present, the adjustment data is filtered, deleting changes to any components except the one that matches the `deploy_to` value found in the control data.

## Development Environment Setup

This project is a Poetry and pyenv project. It requires pyenv and Poetry setup (see ServoX setup documentation).
For convenience, The included Dockerfile sets up all development tools necessary and builds a ready-to-use container based on ServoX.

### Running in development

Set up a token file and a dotenv file:

A typical `.env` file:

```bash
OPSANI_OPTIMIZER=dev.opsani.com/example
OPSANI_TOKEN_FILE=servo.token
```

The `servo.token` file should contain just the servo token.

To run the emulator in bash:

```bash
poetry run servo run
```

## Sample Configuration

When the connectors are set up to be discovered and loaded by ServoX, the configuration format and a sample configuration can be
viewed with the `servo schema` and `servo generate` commands. See https://github.com/opsani/servox.

Here is an example configuration snippet:

```yaml
k8s_env:
  current_mode_namespace: opsani
  current_mode_deployment_name: opsani-servo-qa1-oko-test-ns---qa1-oko-test-app0
  current_mode_annotation: oko.opsani.com/opt_mode
  desired_mode_namespace: qa2-oko-test-ns
  desired_mode_deployment_name: qa2-oko-test-app
  desired_mode_annotation: oko.opsani.com/desired_mode
adjust_filter:
  enable: true
```

## License

Distributed under the terms of the Apache 2.0 Open Source license.

A copy of the license is provided in the [LICENSE](LICENSE) file at the root of
the repository.
