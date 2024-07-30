# Dynamic Stream Operator Generation using OpenAI and SwimOS

Discover how combining the power of <a href="https://openai.com/api/">OpenAI’s</a> ChatGPT with the robust real-time data processing capabilities of <a href="https://www.swimos.org/">SwimOS</a> can transform your data streams into actionable insights on-the-fly. Streaming systems handle continuous and potentially unbounded streams of data, processing each piece of data in upon arrival rather than waiting for the next batch. Stream operators are designed to process data incrementally while taking into account the boundless nature of the stream. They perform various transformations, computations, or aggregations on this real-time data. In this article, we’ll demonstrate how to dynamically generate stream operators using ChatGPT and seamlessly inject them into your application at runtime.

## Technical Overview

Our application consists of the following components:

- **OpenAI ChatGPT**: Utilized for generating stream operator code based on user input.
- **SwimOS**: Handles real-time streaming data and provides a Python client for interacting with Nstream’s SwimOS streaming data application platform.
- **Client code**: A Python script that integrates OpenAI and SwimOS to facilitate dynamic stream operator generation.

## Code Walkthrough

### Dependencies

We start by importing the required libraries, including `openai` for ChatGPT and `swimos` for SwimOS. We also load environment variables from a `.env` file, which contains our OpenAI API key.

```python
import json
import os
import re
import time

from dotenv import load_dotenv
from openai import OpenAI
from swimos import SwimClient
```

### SwimOS and OpenAI Client Setup

We initialize the SwimOS client, specifying the host URI for either the live or simulated feed. We configure two stock data feeds: a 24/7 simulated feed and a live feed, commented out, available during market hours.

```python
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
```

### Downlink Setup

We create a downlink using the SwimOS Python client, providing a callback function to receive updates. We synchronize on the initialization of the Swim client before returning. We also set up a callback function to know when we are ready to receive updates.

```python
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
```

### ChatGPT Code Generation

We define a function to generate code using ChatGPT. We utilize a retry loop to handle requests to ChatGPT, as the responses can be unpredictable. We make a call to the `chat.completions.create` endpoint and ensure we extract only the JSON data using a regular expression.

```python
def generate_llm_code(
    prompt: str,
    expect_json: bool = False,
    max_retries: int = 3, 
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
```

### Dynamic Function Generation

We ask ChatGPT to dynamically generate Python code for a stream operator. This approach provides flexibility, allowing us to handle various data processing needs dynamically without redeploying the application. Specifically, we request a function to maintain a simple moving average with a window size of 5.

```python
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
```

## Conclusion

In this article, we demonstrated how to integrate OpenAI's ChatGPT and SwimOS for dynamic stream operator generation. By leveraging ChatGPT's code generation capabilities and SwimOS's real-time streaming data processing, we can create efficient and scalable data processing pipelines for ad-hoc use cases.

Now it's your turn! Try implementing these patterns in your own projects and see the benefits of dynamic, real-time data processing firsthand.

To learn more about SwimOS, please visit <a href="https://www.swimos.org/">https://www.swimos.org/</a>
