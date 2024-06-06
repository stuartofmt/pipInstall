import json

fn = './test.json'
with open(fn) as jsonfile:
  config = json.load(jsonfile)

print(config)
module_list = config['sbcPythonDependencies']

for i in module_list:
  print(i)
