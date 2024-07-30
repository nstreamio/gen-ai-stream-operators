#!/Users/fredpatton/.pyenv/shims/python

# For blog post: Dynamic Stream Operator Generation using OpenAI and SwimOS
import json
import os
import re
import time

from dotenv import load_dotenv
from openai import OpenAI
from swimos import SwimClient

# Load environment variables from .env file
load_dotenv()

# host_uri = "wss://stocks-live.nstream-demo.io"    # live feed during market hours
host_uri = "wss://stocks-simulated.nstream-demo.io" # simulated feed 24/7
current_exchange_rate = 1.2
current_alert_threshold = 50.0
synced = False

llm_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
swim_client = SwimClient(debug=True)
swim_client.start()


def wait_did_sync():
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
    value_downlink.did_sync(wait_did_sync)
    value_downlink.open()
    while not synced:
        time.sleep(1)
    return value_downlink


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


def accumulate_generate(symbol: str, streaming_operator: str, parameters: dict):
    """Generate a function to accumulate stock prices (min/max/avg) using LLM"""
    global acc
    acc = {}

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

    # Generate and save a dynamic function
    local_vars = {}
    exec(function_code_str, {}, local_vars)
    func_name = function_code_str.split('(')[0].split()[1]
    func = local_vars[func_name]

    def accumulate_generate_callback(new_value: dict, _old_value: dict):
        global acc
        print(f"accumulate_generate_callback received for {symbol}: {new_value}.\n")
        acc, summary = func(acc, new_value['price'], parameters)
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


if __name__ == "__main__":
    result = accumulate_generate("AAAA", "simple moving average", {"window_size": 5})
    print(result)
    
    example_output = """
    crag_patterns % python3 snippet.py 
    Streaming data, press Ctrl+C to stop
    accumulate_generate_callback received for AAAA: {'timestamp': 1721672101793, 'price': 26.01, 'volume': 4597909.036889386, 'bid': 23.57, 'ask': 23.49, 'movement': -38.87}.
    
    AAAA -- summary: 26.01; acc: {'values': [26.01]}
    accumulate_generate_callback received for AAAA: {'timestamp': 1721672105593, 'price': 1.52, 'volume': 8001397.9603691455, 'bid': 19.52, 'ask': 14.94, 'movement': -24.49}.
    
    AAAA -- summary: 13.765; acc: {'values': [26.01, 1.52]}
    accumulate_generate_callback received for AAAA: {'timestamp': 1721672122991, 'price': 85.87, 'volume': 2152727.4653413896, 'bid': 53.12, 'ask': 66.2, 'movement': 84.35}.
    
    AAAA -- summary: 37.800000000000004; acc: {'values': [26.01, 1.52, 85.87]}
    accumulate_generate_callback received for AAAA: {'timestamp': 1721672123792, 'price': 91.88, 'volume': <swimos.structures._structs._Absent object at 0x105354ce0>, 'bid': 11.16, 'ask': 91.88, 'movement': 6}.
    
    AAAA -- summary: 51.32; acc: {'values': [26.01, 1.52, 85.87, 91.88]}
    accumulate_generate_callback received for AAAA: {'timestamp': 1721672134092, 'price': 96.04, 'volume': 376993.84042837605, 'bid': 57.28, 'ask': 67.35, 'movement': 4.16}.
    
    AAAA -- summary: 60.263999999999996; acc: {'values': [26.01, 1.52, 85.87, 91.88, 96.04]}
    accumulate_generate_callback received for AAAA: {'timestamp': 1721672145892, 'price': 94.47, 'volume': 8028026.66065849, 'bid': 16.84, 'ask': 49.37, 'movement': -1.58}.
    
    AAAA -- summary: 73.956; acc: {'values': [1.52, 85.87, 91.88, 96.04, 94.47]}
    accumulate_generate_callback received for AAAA: {'timestamp': 1721672149793, 'price': 99.41, 'volume': <swimos.structures._structs._Absent object at 0x105354ce0>, 'bid': 9.12, 'ask': 50.87, 'movement': 4.93}.
    
    AAAA -- summary: 93.534; acc: {'values': [85.87, 91.88, 96.04, 94.47, 99.41]}
    """