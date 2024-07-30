from swimos import SwimClient
import time

swim_client = SwimClient(debug=True)
swim_client.start()

if __name__ == '__main__':
    host_uri = 'wss://stocks-simulated.nstream-demo.io'
    node_uri = '/stock/AAAA'

    print(node_uri)
    value_downlink = swim_client.downlink_value()
    value_downlink.set_host_uri(host_uri)
    value_downlink.set_node_uri(node_uri)
    value_downlink.set_lane_uri('status')
    value_downlink.open()
    result = value_downlink.get()
    print(f"result: {result}")
    time.sleep(5)
    result = value_downlink.get()
    print(f"result: {result}")
    time.sleep(5)
