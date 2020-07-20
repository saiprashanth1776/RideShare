from requests import get,post,delete,put

# req={"username":"vishwas","password":"2b76bc65a367ae587b4d60d0c8278403f4f61efa"}
# req={"username":"testing","password":"2b76bc65a367ae587b4d60d0c8278403f4f61efa"}
# req={"username":"vishwas","password":"hello"}
# req={}
req={"hello":1}
# req={"created_by":"testing","timestamp":"26-02-2020:00-53-09","source":22,"destination":23}
# req={"created_by":"nobody","timestamp":"26-01-2020:00-53-09","source":22,"destination":23}
# req={"created_by":"nobody","timestamp":"2020-01-26:00-53-09","source":22,"destination":23}
# req={"created_by":"testing","timestamp":"26-01-2020:00-53-09","source":890,"destination":7836}
# req={"created_by":"testing","timestamp":"26-01-2020:00-53-09","source":22,"destination":22}
# req={"created_by":"testing","source":22,"destination":23}
# req={"created_by":"testing","source":22,"destination":23,"random_field":69}
# req={"username":"testing"}
# req={"username":"blehblehbleh"}

# apnd1="vishwas"
# apnd1="thanos"
# apnd1='22';apnd2='23'
# apnd1='48';apnd2='59'
# apnd1='1000';apnd2='100'
apnd1='1'
# apnd1='1000'
# apnd1='5'

s="http://localhost:4000/api/v1/"
# a1=s+'users'
# a2=s+'users/'+apnd1
# a3=s+'rides'
# a4=s+'rides?source='+apnd1+'&destination='+apnd2
a5=s+'rides/'+apnd1

# res=get(a5,json=req)
# res=post(a5,json=req)
res=delete(a5,json=req)
# res=put(a1,json=req)

print(res.status_code,res.json())