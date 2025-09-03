from feast import Entity, ValueType

# Map Feast entities to your dataframe column names
driver = Entity(name="driver", value_type=ValueType.STRING, join_keys=["Driver"])
grand_prix = Entity(name="grand_prix", value_type=ValueType.STRING, join_keys=["GrandPrix"])
lap_number = Entity(name="lap_number", value_type=ValueType.INT64, join_keys=["LapNumber"])
