import os
import sys
import time
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))

from helpers.cluster import ClickHouseCluster

cluster = ClickHouseCluster(__file__)
node = cluster.add_instance("node", stay_alive=True, main_configs=[])


def skip_test_msan(instance):
    if instance.is_built_with_memory_sanitizer():
        pytest.skip("Memory Sanitizer cannot work with vfork")


def copy_file_to_container(local_path, dist_path, container_id):
    os.system(
        "docker cp {local} {cont_id}:{dist}".format(
            local=local_path, cont_id=container_id, dist=dist_path
        )
    )


config = """<clickhouse>
    <user_defined_executable_functions_config>/etc/clickhouse-server/functions/test_function_config.xml</user_defined_executable_functions_config>
</clickhouse>"""


@pytest.fixture(scope="module")
def started_cluster():
    try:
        cluster.start()

        node.replace_config(
            "/etc/clickhouse-server/config.d/executable_user_defined_functions_config.xml",
            config,
        )

        copy_file_to_container(
            os.path.join(SCRIPT_DIR, "functions/."),
            "/etc/clickhouse-server/functions",
            node.docker_id,
        )
        copy_file_to_container(
            os.path.join(SCRIPT_DIR, "user_scripts/."),
            "/var/lib/clickhouse/user_scripts",
            node.docker_id,
        )

        node.restart_clickhouse()

        yield cluster

    finally:
        cluster.shutdown()


def test_executable_function_bash(started_cluster):
    skip_test_msan(node)
    assert node.query("SELECT test_function_bash(toUInt64(1))") == "Key 1\n"
    assert node.query("SELECT test_function_bash(1)") == "Key 1\n"

    assert node.query("SELECT test_function_pool_bash(toUInt64(1))") == "Key 1\n"
    assert node.query("SELECT test_function_pool_bash(1)") == "Key 1\n"


def test_executable_function_python(started_cluster):
    skip_test_msan(node)
    assert node.query("SELECT test_function_python(toUInt64(1))") == "Key 1\n"
    assert node.query("SELECT test_function_python(1)") == "Key 1\n"

    assert node.query("SELECT test_function_pool_python(toUInt64(1))") == "Key 1\n"
    assert node.query("SELECT test_function_pool_python(1)") == "Key 1\n"


def test_executable_function_send_chunk_header_python(started_cluster):
    skip_test_msan(node)
    assert (
        node.query("SELECT test_function_send_chunk_header_python(toUInt64(1))")
        == "Key 1\n"
    )
    assert node.query("SELECT test_function_send_chunk_header_python(1)") == "Key 1\n"

    assert (
        node.query("SELECT test_function_send_chunk_header_pool_python(toUInt64(1))")
        == "Key 1\n"
    )
    assert (
        node.query("SELECT test_function_send_chunk_header_pool_python(1)") == "Key 1\n"
    )


def test_executable_function_sum_python(started_cluster):
    skip_test_msan(node)
    assert (
        node.query("SELECT test_function_sum_python(toUInt64(1), toUInt64(1))") == "2\n"
    )
    assert node.query("SELECT test_function_sum_python(1, 1)") == "2\n"

    assert (
        node.query("SELECT test_function_sum_pool_python(toUInt64(1), toUInt64(1))")
        == "2\n"
    )
    assert node.query("SELECT test_function_sum_pool_python(1, 1)") == "2\n"


def test_executable_function_argument_python(started_cluster):
    skip_test_msan(node)
    assert (
        node.query("SELECT test_function_argument_python(toUInt64(1))") == "Key 1 1\n"
    )
    assert node.query("SELECT test_function_argument_python(1)") == "Key 1 1\n"

    assert (
        node.query("SELECT test_function_argument_pool_python(toUInt64(1))")
        == "Key 1 1\n"
    )
    assert node.query("SELECT test_function_argument_pool_python(1)") == "Key 1 1\n"


def test_executable_function_signalled_python(started_cluster):
    skip_test_msan(node)
    assert node.query_and_get_error(
        "SELECT test_function_signalled_python(toUInt64(1))"
    )
    assert node.query_and_get_error("SELECT test_function_signalled_python(1)")

    assert node.query_and_get_error(
        "SELECT test_function_signalled_pool_python(toUInt64(1))"
    )
    assert node.query_and_get_error("SELECT test_function_signalled_pool_python(1)")


def test_executable_function_slow_python(started_cluster):
    skip_test_msan(node)
    assert node.query_and_get_error("SELECT test_function_slow_python(toUInt64(1))")
    assert node.query_and_get_error("SELECT test_function_slow_python(1)")

    assert node.query_and_get_error(
        "SELECT test_function_slow_pool_python(toUInt64(1))"
    )
    assert node.query_and_get_error("SELECT test_function_slow_pool_python(1)")


def test_executable_function_non_direct_bash(started_cluster):
    skip_test_msan(node)
    assert node.query("SELECT test_function_non_direct_bash(toUInt64(1))") == "Key 1\n"
    assert node.query("SELECT test_function_non_direct_bash(1)") == "Key 1\n"

    assert (
        node.query("SELECT test_function_non_direct_pool_bash(toUInt64(1))")
        == "Key 1\n"
    )
    assert node.query("SELECT test_function_non_direct_pool_bash(1)") == "Key 1\n"


def test_executable_function_sum_json_python(started_cluster):
    skip_test_msan(node)

    node.query("DROP TABLE IF EXISTS test_table;")
    node.query("CREATE TABLE test_table (lhs UInt64, rhs UInt64) ENGINE=TinyLog;")
    node.query("INSERT INTO test_table VALUES (0, 0), (1, 1), (2, 2);")

    assert (
        node.query("SELECT test_function_sum_json_unnamed_args_python(1, 2);") == "3\n"
    )
    assert (
        node.query(
            "SELECT test_function_sum_json_unnamed_args_python(lhs, rhs) FROM test_table;"
        )
        == "0\n2\n4\n"
    )

    assert (
        node.query("SELECT test_function_sum_json_partially_named_args_python(1, 2);")
        == "3\n"
    )
    assert (
        node.query(
            "SELECT test_function_sum_json_partially_named_args_python(lhs, rhs) FROM test_table;"
        )
        == "0\n2\n4\n"
    )

    assert node.query("SELECT test_function_sum_json_named_args_python(1, 2);") == "3\n"
    assert (
        node.query(
            "SELECT test_function_sum_json_named_args_python(lhs, rhs) FROM test_table;"
        )
        == "0\n2\n4\n"
    )

    assert (
        node.query("SELECT test_function_sum_json_unnamed_args_pool_python(1, 2);")
        == "3\n"
    )
    assert (
        node.query(
            "SELECT test_function_sum_json_unnamed_args_pool_python(lhs, rhs) FROM test_table;"
        )
        == "0\n2\n4\n"
    )

    assert (
        node.query("SELECT test_function_sum_json_partially_named_args_python(1, 2);")
        == "3\n"
    )
    assert (
        node.query(
            "SELECT test_function_sum_json_partially_named_args_python(lhs, rhs) FROM test_table;"
        )
        == "0\n2\n4\n"
    )

    assert (
        node.query("SELECT test_function_sum_json_named_args_pool_python(1, 2);")
        == "3\n"
    )
    assert (
        node.query(
            "SELECT test_function_sum_json_named_args_pool_python(lhs, rhs) FROM test_table;"
        )
        == "0\n2\n4\n"
    )

    node.query("DROP TABLE test_table;")


def test_executable_function_input_nullable_python(started_cluster):
    skip_test_msan(node)

    node.query("DROP TABLE IF EXISTS test_table_nullable;")
    node.query(
        "CREATE TABLE test_table_nullable (value Nullable(UInt64)) ENGINE=TinyLog;"
    )
    node.query("INSERT INTO test_table_nullable VALUES (0), (NULL), (2);")

    assert (
        node.query(
            "SELECT test_function_nullable_python(1), test_function_nullable_python(NULL)"
        )
        == "Key 1\tKey Nullable\n"
    )
    assert (
        node.query(
            "SELECT test_function_nullable_python(value) FROM test_table_nullable;"
        )
        == "Key 0\nKey Nullable\nKey 2\n"
    )

    assert (
        node.query(
            "SELECT test_function_nullable_pool_python(1), test_function_nullable_pool_python(NULL)"
        )
        == "Key 1\tKey Nullable\n"
    )
    assert (
        node.query(
            "SELECT test_function_nullable_pool_python(value) FROM test_table_nullable;"
        )
        == "Key 0\nKey Nullable\nKey 2\n"
    )

    node.query("DROP TABLE test_table_nullable;")


def test_executable_function_parameter_python(started_cluster):
    skip_test_msan(node)

    assert node.query_and_get_error(
        "SELECT test_function_parameter_python(2,2)(toUInt64(1))"
    )
    assert node.query_and_get_error("SELECT test_function_parameter_python(2,2)(1)")
    assert node.query_and_get_error("SELECT test_function_parameter_python(1)")
    assert node.query_and_get_error(
        "SELECT test_function_parameter_python('test')(toUInt64(1))"
    )

    assert (
        node.query("SELECT test_function_parameter_python('2')(toUInt64(1))")
        == "Parameter 2 key 1\n"
    )
    assert (
        node.query("SELECT test_function_parameter_python(2)(toUInt64(1))")
        == "Parameter 2 key 1\n"
    )


def test_executable_function_always_error_python(started_cluster):
    skip_test_msan(node)
    try:
        node.query("SELECT test_function_always_error_throw_python(1)")
        assert False, "Exception have to be thrown"
    except Exception as ex:
        assert "DB::Exception: Executable generates stderr: Fake error" in str(ex)

    query_id = uuid.uuid4().hex
    assert (
        node.query("SELECT test_function_always_error_log_python(1)", query_id=query_id)
        == "Key 1\n"
    )
    assert node.contains_in_log(
        f"{{{query_id}}} <Warning> TimeoutReadBufferFromFileDescriptor: Executable generates stderr: Fake error"
    )

    query_id = uuid.uuid4().hex
    assert (
        node.query(
            "SELECT test_function_always_error_log_first_python(1)", query_id=query_id
        )
        == "Key 1\n"
    )
    assert node.contains_in_log(
        f"{{{query_id}}} <Warning> TimeoutReadBufferFromFileDescriptor: Executable generates stderr at the beginning:  {'a' * (3 * 1024)}{'b' * 1024}\n"
    )

    query_id = uuid.uuid4().hex
    assert (
        node.query(
            "SELECT test_function_always_error_log_last_python(1)", query_id=query_id
        )
        == "Key 1\n"
    )
    assert node.contains_in_log(
        f"{{{query_id}}} <Warning> TimeoutReadBufferFromFileDescriptor: Executable generates stderr at the end:  {'b' * 1024}{'c' * (3 * 1024)}\n"
    )

    assert node.query("SELECT test_function_exit_error_ignore_python(1)") == "Key 1\n"

    try:
        node.query("SELECT test_function_exit_error_fail_python(1)")
        assert False, "Exception have to be thrown"
    except Exception as ex:
        assert "DB::Exception: Child process was exited with return code 1" in str(ex)

def test_executable_function_query_cache(started_cluster):
    '''Test for issues #77553 and #59988: Users should be able to specify if externally-defined are non-deterministic, and the query cache should treat them correspondingly.'''
    '''Also see tests/0_stateless/test_query_cache_udf_sql.sql'''
    skip_test_msan(node)

    node.query("SYSTEM DROP QUERY CACHE");

    # we are each testing an UDF without explicit <deterministic> tag (to check the default behavior) and two queries with <deterministic> true respectively false </deterministic>.

    # query_cache_nondeterministic_function_handling = throw

    assert node.query_and_get_error("SELECT test_function_bash(1) SETTINGS use_query_cache = true, query_cache_nondeterministic_function_handling = 'throw'")
    assert node.query("SELECT count(*) FROM system.query_cache") == "0\n"

    assert node.query("SELECT test_function_bash_deterministic(1) SETTINGS use_query_cache = true, query_cache_nondeterministic_function_handling = 'throw'") == "Key 1\n"
    assert node.query("SELECT count(*) FROM system.query_cache") == "1\n"

    assert node.query_and_get_error("SELECT test_function_bash_nondeterministic(1) SETTINGS use_query_cache = true, query_cache_nondeterministic_function_handling = 'throw'")
    assert node.query("SELECT count(*) FROM system.query_cache") == "1\n"

    node.query("SYSTEM DROP QUERY CACHE");

    # query_cache_nondeterministic_function_handling = save

    assert node.query("SELECT test_function_bash(1) SETTINGS use_query_cache = true, query_cache_nondeterministic_function_handling = 'save'") == "Key 1\n"
    assert node.query("SELECT count(*) FROM system.query_cache") == "1\n"

    assert node.query("SELECT test_function_bash_deterministic(1) SETTINGS use_query_cache = true, query_cache_nondeterministic_function_handling = 'save'") == "Key 1\n"
    assert node.query("SELECT count(*) FROM system.query_cache") == "2\n"

    assert node.query("SELECT test_function_bash_nondeterministic(1) SETTINGS use_query_cache = true, query_cache_nondeterministic_function_handling = 'save'") == "Key 1\n"
    assert node.query("SELECT count(*) FROM system.query_cache") == "3\n"

    node.query("SYSTEM DROP QUERY CACHE");

    # query_cache_nondeterministic_function_handling = ignore

    assert node.query("SELECT test_function_bash(1) SETTINGS use_query_cache = true, query_cache_nondeterministic_function_handling = 'ignore'") == "Key 1\n"
    assert node.query("SELECT count(*) FROM system.query_cache") == "0\n"

    assert node.query("SELECT test_function_bash_deterministic(1) SETTINGS use_query_cache = true, query_cache_nondeterministic_function_handling = 'ignore'") == "Key 1\n"
    assert node.query("SELECT count(*) FROM system.query_cache") == "1\n"

    assert node.query("SELECT test_function_bash_nondeterministic(1) SETTINGS use_query_cache = true, query_cache_nondeterministic_function_handling = 'ignore'") == "Key 1\n"
    assert node.query("SELECT count(*) FROM system.query_cache") == "1\n"

    node.query("SYSTEM DROP QUERY CACHE");
