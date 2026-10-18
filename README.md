## To build Dockerfile

```
docker build \
--progress=plain \
-t embroidery-server:inkstitch-3.2.2 \
./server


## To run Dockerfile
```

docker run --rm \
--name embroidery-server \
-p 8000:8000 \
embroidery-server:inkstitch-3.2.2

```

```

```

```
