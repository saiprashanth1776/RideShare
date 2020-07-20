# Check if docker is running
if ! docker info > /dev/null
then
  echo "Docker is not running!"
fi

echo "Stopping RideShare..."

cd dbaas || exit

echo "Step 1/2: Stopping Containers..."
docker-compose down &> /dev/null
docker stop users > /dev/null
docker stop rides > /dev/null
docker stop bunny > /dev/null
docker stop zook > /dev/null
echo "Step 1/2: Done."
echo "Step 2/2: Removing spawned containers."
if [[ $(docker container ps -aq --filter ancestor=worker) ]]; then
  docker container rm --force $(docker ps -aq --filter ancestor=worker)  > /dev/null
fi
echo "Step 2/2: Done."
docker image prune -f > /dev/null
echo "RideShare shutdown complete."
