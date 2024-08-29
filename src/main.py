#!/Users/fredpatton/.pyenv/shims/python

import json
import os
import re
import time

import typer
from dotenv import load_dotenv
from openai import OpenAI
from swimos import SwimClient

# Load environment variables from .env file
load_dotenv()

app = typer.Typer()
host_uri = "wss://stocks-simulated.nstream-demo.io"
current_exchange_rate = 1.2
current_alert_threshold = 50.0
synced = False

# Initialize OpenAI client
llm_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
swim_client = SwimClient(debug=True)
swim_client.start()


def print_did_sync():
    global synced
    synced = True


def setup_value_downlink(node_uri: str, callback=None):
    global swim_client
    global synced
    value_downlink = swim_client.downlink_value()
    value_downlink.set_host_uri(host_uri)
    value_downlink.set_node_uri(node_uri)
    value_downlink.set_lane_uri("status")
    if callback is not None:
        value_downlink.did_set(callback)
    value_downlink.did_sync(print_did_sync)
    value_downlink.open()
    while not synced:
        time.sleep(1)
    return value_downlink


@app.command()
def read_adhoc(symbol: str):
    """Read stock prices for a given symbol (ad-hoc)"""
    node_uri = f"/stock/{symbol}"
    value_downlink = setup_value_downlink(node_uri)
    result = value_downlink.get(symbol)
    print(f"Ad-hoc read result for {symbol} is: {result['price']}\n")
    value_downlink.close()
    raise typer.Abort()


def streaming_read_callback(new_value: dict, _old_value: dict):
    print(f"Streaming read result is: {new_value['price']}\n")


@app.command()
def read_streaming(symbol: str):
    """Read stock prices for a given symbol (streaming)"""
    node_uri = f"/stock/{symbol}"
    print('Streaming data, press Ctrl+C to stop')
    value_downlink = setup_value_downlink(node_uri, streaming_read_callback)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        value_downlink.close()
        print('Streaming stopped')


def generate_llm_code(prompt: str, expect_json: bool = False, max_retries: int = 3, retry_delay: int = 1):
    retries = 0
    while retries < max_retries:
        try:
            response = llm_client.chat.completions.create(
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                model="gpt-4",
                max_tokens=1000
            )
            response_content = response.choices[0].message.content.strip()

            if expect_json:
                # Use regex to extract JSON object with non-greedy match
                json_match = re.search(
                    r'\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\}',
                    response_content, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                    try:
                        result = json.loads(json_str)
                        return result['result'] if 'result' in result else result
                    except (json.JSONDecodeError, KeyError) as e:
                        raise ValueError("Failed to decode JSON from LLM response") from e
                else:
                    raise ValueError("No valid JSON found in LLM response")
            else:
                return response_content

        except Exception as e:
            retries += 1
            print(f"Error: {e}, retrying... ({retries}/{max_retries})")
            time.sleep(retry_delay)

    raise ValueError("Max retries exceeded, failed to get valid response from LLM")


@app.command()
def map_direct(symbol: str, operation_config: str):
    """Map stock prices to a different unit using LLM (direct invocation)"""
    global current_operation_config

    # Parse the operation_config JSON string
    try:
        current_operation_config = json.loads(operation_config)
    except json.JSONDecodeError:
        print("Invalid operation_config. Please provide a valid JSON string.")
        return

    node_uri = f"/stock/{symbol}"

    def map_direct_callback(new_value: dict, _old_value: dict):
        print(new_value)
        # Extract operation and parameters from operation_config
        operation_details = current_operation_config

        # Form the prompt dynamically based on operation details
        operation_description = current_operation_config.get(
            "description",
            "Perform a custom operation")
        parameters = json.dumps(current_operation_config.get("parameters", {}))

        prompt = f"""
        {operation_description}
        The current stock price is {new_value['price']}.
        The parameters for this operation are: {parameters}.
        Please perform the operation and return a JSON object with `result` as 
        the only key and storing the result of the operation.
        All other keys will be ignored. Please only provide JSON.
        """

        result = generate_llm_code(prompt, expect_json=True)
        print(f"Mapped {new_value['price']} to {result}.\n")

    print('Streaming data, press Ctrl+C to stop')
    value_downlink = setup_value_downlink(node_uri, map_direct_callback)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        value_downlink.close()
        print('Streaming stopped')


@app.command()
def filter_direct(symbol: str, operation_config: str):
    """Filter stock prices based on a condition using LLM (direct invocation)"""
    global current_operation_config

    # Parse the operation_config JSON string
    try:
        current_operation_config = json.loads(operation_config)
    except json.JSONDecodeError:
        print("Invalid operation_config. Please provide a valid JSON string.")
        return

    node_uri = f"/stock/{symbol}"

    def filter_direct_callback(new_value: dict, _old_value: dict):
        print(new_value)
        # Extract operation and parameters from operation_config
        operation_details = current_operation_config

        # Form the prompt dynamically based on operation details
        operation_description = current_operation_config.get(
            "description",
            "Perform a custom filter operation")
        parameters = json.dumps(current_operation_config.get("parameters", {}))

        prompt = f"""
        {operation_description}
        The current stock price is {new_value['price']}.
        The parameters for this operation are: {parameters}.
        Perform the operation and return a JSON object with `result` as the only
        top-level key. It's value the string 'true' or 'false' based on the result of filtering.
        All other keys will be ignored. Please only provide JSON.
        """

        result = generate_llm_code(prompt, expect_json=True)
        if result.lower() == 'true':
            print(f"Price {new_value['price']} meets the filter criteria.\n")

    print('Streaming data, press Ctrl+C to stop')
    value_downlink = setup_value_downlink(node_uri, filter_direct_callback)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        value_downlink.close()
        print('Streaming stopped')


@app.command()
def accumulate_direct(
        symbol: str,
        streaming_operator: str,
        operation_config: str = typer.Option(
            "{}",
            help="JSON string with parameters for the operation")):
    """Accumulate stock prices (like min/max/avg) using LLM (direct invocation)"""
    global acc
    acc = {}

    # Parse the operation_config JSON string
    try:
        current_operation_config = json.loads(operation_config)
    except json.JSONDecodeError:
        print("Invalid operation_config. Please provide a valid JSON string.")
        return

    def accumulate_direct_callback(new_value: dict, _old_value: dict):
        global acc
        print(new_value)

        parameters = json.dumps(current_operation_config)

        prompt = f"""
        Perform the {streaming_operator} accumulation operation.
        The current stock price is {new_value['price']}.
        The current accumulator state is {acc}.
        The parameters for this operation are: {parameters}.
        If the accumulator is empty, initialize it appropriately for the 
        {streaming_operator} operation. Please perform the operation and return 
        a JSON object with `result` as the only key. Under `result` provide 
        'summary` for the result of the operation and `acc` for the updated 
        accumulator. All other keys will be ignored. Please only provide JSON.
        """
        response = generate_llm_code(prompt, expect_json=True)

        acc = response['acc']
        summary = response['summary']
        print(f"Result for {symbol}: summary: {summary}; acc: {acc}.\n")

    node_uri = f"/stock/{symbol}"
    print('Streaming data, press Ctrl+C to stop')
    value_downlink = setup_value_downlink(node_uri, accumulate_direct_callback)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        value_downlink.close()
        print('Streaming stopped')


@app.command()
def map_generate(symbol: str, operation_config: str):
    """Generate a function to map stock prices to a different unit using LLM"""
    global current_operation_config

    # Parse the operation_config JSON string
    try:
        current_operation_config = json.loads(operation_config)
    except json.JSONDecodeError:
        print("Invalid operation_config. Please provide a valid JSON string.")
        return

    description = current_operation_config.get("description", "Perform a mapping operation")
    parameters = json.dumps(current_operation_config.get("parameters", {}))

    prompt = f"""
    Return a JSON result, and only a JSON result that has a single key: `result`. 
    In this `result` key, store a string that contains a Python function with the 
    following signature `def func(new_value: float, operation_config: dict):`. 
    The implementation must apply the exchange rate provided in `operation_config` 
    to the `new_value`. The parameters for this operation are: {parameters}.
    Ensure the function is returned as a single line string.
    """
    function_code_str = generate_llm_code(prompt, expect_json=True)

    # Evaluate the function code
    function_code_str = function_code_str.replace("throw", "raise")  # Correct the syntax error
    local_vars = {}
    exec(function_code_str, {}, local_vars)
    func_name = function_code_str.split('(')[0].split()[1]
    func = local_vars[func_name]

    def map_generate_callback(new_value: dict, _old_value: dict):
        print(new_value)
        result = func(new_value['price'], current_operation_config['parameters'])
        print(f"The price {new_value['price']} has been converted to {result}.\n")

    node_uri = f"/stock/{symbol}"
    print('Streaming data, press Ctrl+C to stop')
    value_downlink = setup_value_downlink(node_uri, map_generate_callback)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        value_downlink.close()
        print('Streaming stopped')


@app.command()
def filter_generate(symbol: str, operation_config: str):
    """Generate a function to filter stock prices based on a condition using LLM"""
    global current_operation_config

    # Parse the operation_config JSON string
    try:
        current_operation_config = json.loads(operation_config)
    except json.JSONDecodeError:
        print("Invalid operation_config. Please provide a valid JSON string.")
        return

    description = current_operation_config.get(
        "description",
        "Perform a filter operation")
    parameters = json.dumps(current_operation_config.get("parameters", {}))

    prompt = f"""
    Return a JSON result, and only a JSON result that has a single key: `result`. 
    In this `result` key, store a string that contains a Python function with the 
    following signature `def func(new_value: float, operation_config: dict):` and the 
    implementation must be as follows: {description}. Use the parameters provided 
    in `operation_config` to determine the filtering criteria. The function should 
    return a string 'true' if the new_value meets the criteria, otherwise 'false'.
    The parameters for this operation are: {parameters}.
    Ensure the function is returned as a single line string.
    """
    function_code_str = generate_llm_code(prompt, expect_json=True)

    # Evaluate the function code
    local_vars = {}
    exec(function_code_str, {}, local_vars)
    func_name = function_code_str.split('(')[0].split()[1]
    func = local_vars[func_name]

    def filter_generate_callback(new_value: dict, _old_value: dict):
        print(new_value)
        result = func(new_value['price'], current_operation_config['parameters'])
        if result.lower() == 'true':
            print(f"The price {new_value['price']} has met the filter criteria.\n")

    node_uri = f"/stock/{symbol}"
    print('Streaming data, press Ctrl+C to stop')
    value_downlink = setup_value_downlink(node_uri, filter_generate_callback)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        value_downlink.close()
        print('Streaming stopped')


@app.command()
def accumulate_generate(
        symbol: str,
        streaming_operator: str,
        operation_config: str = typer.Option(
            "{}",
            help="JSON string with parameters for the operation")):
    """Generate a function to accumulate stock prices (min/max/avg) using LLM"""
    global acc
    acc = {}

    # Parse the operation_config JSON string
    try:
        current_operation_config = json.loads(operation_config)
    except json.JSONDecodeError:
        print("Invalid operation_config. Please provide a valid JSON string.")
        return

    parameters = json.dumps(current_operation_config)

    prompt = f"""
    Return a JSON result, and only a JSON result. The JSON must have a single 
    top-level key: `result`. In this `result` key, store a string that contains 
    a python function with the following signature 
    `def func(acc: dict, new_value: float, params: dict):` 
    and the implementation must be as follows: calculate the {streaming_operator}
    on `new_value` given accumulator state of `acc` that your function has
    defined in order to continue applying the {streaming_operator} as each new
    value arrives. Your function must return a tuple consisting of `acc` followed
    by the result of its calculation. The parameters for this operation are: {parameters}.
    """
    function_code_str = generate_llm_code(prompt, expect_json=True)

    # Evaluate the function code
    local_vars = {}
    exec(function_code_str, {}, local_vars)
    func_name = function_code_str.split('(')[0].split()[1]
    func = local_vars[func_name]

    def accumulate_generate_callback(new_value: dict, _old_value: dict):
        global acc
        print(f"accumulate_generate_callback received for {symbol}: {new_value}.\n")
        acc, summary = func(acc, new_value['price'], current_operation_config)
        print(f"{symbol} -- summary: {summary}; acc: {acc}")

    node_uri = f"/stock/{symbol}"
    print('Streaming data, press Ctrl+C to stop')
    value_downlink = setup_value_downlink(node_uri, accumulate_generate_callback)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        value_downlink.close()
        print('Streaming stopped')


def generate_llm_code_for_execute(
        prompt: str,
        max_retries: int = 5,
        retry_delay: int = 1):
    retries = 0
    while retries < max_retries:
        try:
            response = llm_client.chat.completions.create(
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                model="gpt-4",
                max_tokens=1000
            )
            response_content = response.choices[0].message.content.strip()
            print(f"response_content: {response_content}")

            # Use regex to extract JSON object with non-greedy match
            json_match = re.search(
                r'\{.*\}',
                # r'\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\}',
                response_content, re.DOTALL)

            if json_match:
                json_str = json_match.group(0)
                try:
                    result = json.loads(json_str)
                    return result  # Directly returning the parsed JSON result
                except (json.JSONDecodeError, KeyError) as e:
                    raise ValueError("Failed to decode JSON from LLM response") from e
            else:
                raise ValueError("No valid JSON found in LLM response")

        except Exception as e:
            retries += 1
            print(f"Error: {e}, retrying... ({retries}/{max_retries})")
            time.sleep(retry_delay)

    raise ValueError("Max retries exceeded, failed to get valid response from LLM")


def invoke_llm_to_process_command(command: str, generate_llm_code_func):
    prompt = f"""
    You are an intelligent assistant that converts natural language commands 
    into structured code for various functions.
    You must only return valid JSON. Only valid JSON.
    Given the command: '{command}', determine which function to execute and 
    provide the necessary parameters in JSON format and identify the name of 
    the function in the JSON response using the `function` field.
    When choosing functions with the suffix "_direct" and "_generate", choose
    the latter whenever the request is asking for code (function, operator, etc).

    Possible functions:
    - read_adhoc(symbol: str)
    - read_streaming(symbol: str)
    - map_direct(symbol: str, operation_config: str)
    - map_generate(symbol: str, operation_config: str)
    - filter_direct(symbol: str, operation_config: str)
    - filter_generate(symbol: str, operation_config: str)
    - accumulate_direct(symbol: str, streaming_operator: str, operation_config: str)
    - accumulate_generate(symbol: str, streaming_operator: str, operation_config: str)

    Examples:
    {{\\"function\\": \\"read_adhoc\\", \\"symbol\\": \\"AAAA\\"}}
    {{\\"function\\": \\"read_streaming\\", \\"symbol\\": \\"AAAA\\"}}
    {{\\"function\\": \\"map_direct\\", \\"symbol\\": \\"AAAA\\", \\"operation_config\\": {{\\"description\\": \\"apply exchange rate\\", \\"parameters\\": {{\\"exchange_rate\\": 35}}}}
    {{\\"function\\": \\"filter_direct\\", \\"symbol\\": \\"AAAA\\", \\"operation_config\\": {{\\"description\\": \\"alert me if stock price for AAAA goes below 35\\", \\"parameters\\": {{\\"threshold\\": 35}}}}
    {{\\"function\\": \\"accumulate_direct\\", \\"parameters\\": {{ \\"symbol\\": \\"AAAA\\", \\"streaming_operator\\": \\"average\\", \\"operation_config\\": {{\\"window_size\\": 5}}}}
    {{\\"function\\": \\"map_generate\\", \\"symbol\\": \\"AAAA\\", \\"operation_config\\": {{\\"description\\": \\"apply exchange rate\\", \\"parameters\\": {{\\"exchange_rate\\": 35}}}}
    {{\\"function\\": \\"filter_generate\\", \\"symbol\\": \\"AAAA\\", \\"operation_config\\": {{\\"description\\": \\"alert me if stock price for AAAA goes below 35\\", \\"parameters\\": {{\\"threshold\\": 35}}}}
    {{\\"function": \\"accumulate_generate\\", \\"parameters\\": {{ \\"symbol\\": \\"AAAA\\", \\"streaming_operator\\": \\"average\\", \\"operation_config\\": {{\\"window_size\\": 5}}}}

    Pay attention to the language used.
    For filtering, pay attention to signal terms such as these, as they imply filtering:
    - filter, alert, find, look, match, screen, select, pick, choose, exclude, include, 
      only, except, without, with, containing, not, none, all, any, specific, particular, 
      certain, exactly, matching, like, unlike, different, alert, same, similar, 
      dissimilar, look for, separate, but not, reject, omit, show, give, flag.
    Keep in mind that the context and intent behind the query can also influence the 
    interpretation of these keywords.
    Ensure you have included the key "function" in the JSON object.
    Make sure the JSON you return is valid and parseable.
    """
    response = generate_llm_code_func(prompt)
    return response


@app.command()
def execute(command: str):
    """Execute a command"""
    try:
        # Parse the JSON response from the LLM
        json_response = invoke_llm_to_process_command(
            command,
            generate_llm_code_func=generate_llm_code_for_execute)
        print(f"json_response:\n{json_response}")
        function_name = json_response.get("function", "map_generate")
        parameters = json_response.get("parameters")

        # Extract operation_config if present
        operation_config = None

        if parameters is not None:
            operation_config = parameters.pop("operation_config", None)
        else:
            operation_config = json_response.get("operation_config")

        if operation_config:
            # operation_config = json.loads(operation_config)

            if not parameters:
                parameters = operation_config.get("parameters")
                print(f"* parameters: {parameters}")

        if parameters is None and 'symbol' in json_response:
            parameters = {'symbol': json_response.get('symbol')}

        if not function_name or not parameters:
            raise ValueError("Invalid response from LLM")

        symbol = None
        if 'symbol' in parameters:
            symbol = parameters['symbol']
        elif 'symbol' in json_response:
            symbol = json_response.get('symbol')

        # Call the appropriate function with the provided parameters
        print(f"function_name: {function_name}")
        if function_name == "read_adhoc":
            read_adhoc(**parameters)
        elif function_name == "read_streaming":
            read_streaming(**parameters)
        elif function_name == "map_direct":
            map_direct(symbol, json.dumps(operation_config))
        elif function_name == "map_generate":
            map_generate(symbol, json.dumps(operation_config))
        elif function_name == "filter_direct":
            filter_direct(symbol, json.dumps(operation_config))
        elif function_name == "filter_generate":
            filter_generate(symbol, json.dumps(operation_config))
        elif function_name == "accumulate_direct":
            accumulate_direct(symbol, parameters["streaming_operator"], json.dumps(operation_config))
        elif function_name == "accumulate_generate":
            accumulate_generate(symbol, parameters["streaming_operator"], json.dumps(operation_config))
        else:
            print("Unknown function")
    except ValueError as e:
        print(f"Error: {e}")
        print("Retrying with the same command...")
        execute(command)


if __name__ == "__main__":
    app()
