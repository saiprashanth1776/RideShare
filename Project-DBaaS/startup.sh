# Check if docker is running
if ! docker info > /dev/null
then
  echo "Docker is not running!"
fi

echo "Starting build."
echo "This will take a few minutes if you are running this for the first time."
echo "Please be patient."

echo "Step 1/7: Doing Prior Cleanup..."

docker image prune -f > /dev/null

# Removing any prior worker containers which still remain.
if [[ $(docker container ps -aq --filter ancestor=worker) ]]; then
  docker container rm --force $(docker ps -aq --filter ancestor=worker) > /dev/null
fi

echo "Step 1/7: Done"

echo "Step 2/7: Creating Docker Network..."

#Create Network if it doesn't exist
docker network ls | grep dbaas-net > /dev/null || docker network create dbaas-net > /dev/null

echo "Step 2/7: Done."

echo "Step 3/7: Setting up RabbitMQ and Zookeeper..."
#Check if bunny is exists and is running.
if ! docker container ls --all | grep bunny > /dev/null
then
  docker run -d --name bunny --network dbaas-net rabbitmq  > /dev/null # bunny container doesn't exist at on system.
  echo "Taking a 10s pause while RabbitMQ starts.."
  sleep 10
else
  if ! docker container ls | grep bunny  > /dev/null
  then
    docker restart bunny > /dev/null # bunny container is in exited state, restart.
    echo "Taking a 10s pause while RabbitMQ starts.."
    sleep 10
  fi
fi

#Check if zook is exists and is running.
if ! docker container ls --all | grep zook > /dev/null
then
  docker run -d --name zook --restart always --network dbaas-net zookeeper  > /dev/null # zook container doesn't exist at on system.
  echo "Taking a 10s pause while Zookeeper starts.."
  sleep 10
else
  if ! docker container ls | grep zook  > /dev/null
  then
    docker restart zook > /dev/null # zook container is in exited state, restart.
    echo "Taking a 10s pause while Zookeeper starts.."
    sleep 10
  fi
fi

echo "Step 3/7: Done."

# If Rides and Users containers are running, rebuild and rerun
echo "Step 4/7: Setting up Rides Container..."
cd ./RidesInstance && docker-compose up -d --force-recreate --build > /dev/null && cd ..

echo "Step 4/7: Done."
echo "Step 5/7: Setting up Users Container..."
cd ./UsersInstance && docker-compose up -d --force-recreate --build > /dev/null && cd ..

echo "Step 5/7: Done."

cd dbaas || exit

echo "Step 6/7: Building Images..."
cd base_builder && docker build -t base:latest . > /dev/null && cd ..
cd worker && docker build -t worker:latest . > /dev/null && cd ..
echo "Step 6/7: Done."

echo "Step 7/7: Starting PersDb & Orchestrator Containers..."
docker-compose up --build -d --force-recreate > /dev/null && cd ..
echo "Step 7/7: Done."
echo "RideShare is now running."
