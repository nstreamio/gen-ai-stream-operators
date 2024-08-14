```sh
python main.py execute "Give me the stock price for AAAA"
python main.py execute "Stream stock prices for AAAA"
python main.py execute "Convert stock price for AAAA using an exchange rate of 1.2"
python main.py execute "Create a function to convert stock prices for AAAA with an exchange rate of 1.2"
python main.py execute "Alert me if stock price for AAAA goes below 20"
python main.py execute "Create a function to alert me if stock price for AAAA goes below 20"
python main.py execute "Accumulate stock prices for AAAA using average with a window size of 5"
python main.py execute "Create a function to accumulate stock prices for AAAA using average with a window size of 5"

python main.py read-adhoc AAAA
python main.py read-streaming AAAA
python main.py accumulate-direct AAAA avg --operation-config '{"window_size": 5}'
python main.py accumulate-generate AAAA avg --operation-config '{"window_size": 5}'
python main.py map-direct AAAA '{"description": "apply exchange rate", "parameters": {"exchange_rate": "1.2"}}'
python main.py map-generate AAAA '{"description": "apply exchange rate", "parameters": {"exchange_rate": "1.2"}}'
python main.py filter-direct AAAA '{"description": "flag any values under 20", "parameters": {"threshold": 20}}'
python main.py filter-generate AAAA '{"description": "flag any values under 20", "parameters": {"threshold": 20}}'
```
