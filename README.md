# Scrapper Distribuido

### Requerimientos

- **python zmq**

- **python 3**

### Utilización

**client.py**: La aplicación cliente. Recibe una url insertada por el usuario, además de una profundidad. El cliente scrappea la url con dicha profundidad haciéndole peticiones al servidor. Al terminar, creará unos directorios en la carpeta donde se encuentra el código que seguirá la misma estructura que los links en el código html de la url. 

**Chord_node**: La implementación del nodo chord estudiado en clases. Varios nodos crean una red que actúan como un solo sistema. Reciben peticiones, devuelven el código html de la url, almacenan en cache el código hallado para futuras peticiones repetidas, replican los datos entre ellos y se recuperan de fallas.

El cliente solo conoce la dirección ip de un nodo de la red chord, el cual sería el ip del "sistema".

**Poner en funcionamiento un cliente y una red chord**:

Para ejecutar el archivo client.py es necesario pasarle la dirección ip y puerto donde el cliente se va a alojar y la dirección ip y puerto del sistema al cual va a contactarse.

Ejemplo para un cliente:

```
python3 client.py -my_addr 127.0.0.1:5009 -entry_addr 127.0.0.1:5001
```

Para ejecutar un nodo de Chord_node.py es necesario pasarle el ip y puerto en el cual el nodo va a alojarse, el id del nodo en la red de nodos chord y la cantidad de bits de la red de nodos chord. Un parámetro adicional es la dirección ip y puerto de un nodo ya existente en la red por el cual el nodo actual va a unirse, si no se especifica se asume que se creó una nueva red chord y solo existe el nodo actual. Además del puerto dado de manera externa al ejecutar el código, el nodo también reserva el próximo puerto (por ejemplo si se dedicó el puerto 5000 al nodo, este también reservará el puerto 5001). Un puerto es para recibir peticiones de tipo internas de la red, y otro es para recibir peticiones dedicadas a scrappear el contenido html de una url dada.

Ejemplo para ejecutar una red de nodos chord de tres nodos para tres bits:

```
python3 Chord_node.py -id 0 -addr 127.0.0.1:5000 -bits 3
```

```
python3 Chord_node.py -id 1 -addr 127.0.0.1:5002 -bits 3 -entry_addr 127.0.0.1:5000
```

```
python3 Chord_node.py -id 3 -addr 127.0.0.1:5004 -bits 3 -entry_addr 127.0.0.1:5000
```

### Notas sobre funcionamiento

#### Red de nodos

La implementación del Chord_node.py sigue las ideas ilustradas en el pseudocódigo del artículo: *Chord: A Scalable Peer-to-peer Lookup Service for Internet Applications*. Al cual se le añadió:

- **Tolerancia a fallas:** Cada nodo en la red tiene una lista de `r` sucesores. Cuando un nodo `A` falla, su predecesor `B` buscará en la lista de sucesores un nodo que esté vivo `C`. A continuación, `B` pone como su sucesor a `C` y le notifica que es su predecesor. Al cabo del tiempo la red se estabilizará mediante el método `fix_fingers` cuyo pseudocódigo está en el artículo. Para mantener actualizada la lista de `r` sucesores se implementó un método análogo al `fix_fingers` pero esta vez sobre la lista de sucesores. La búsqueda de `find_predeccesor` ahora toma en cuenta los nodos caídos, y  busca un camino alternativo para encontrar el nodo correspondiente.
- **Replicación**: Cuando un nodo se cae, sus datos asociados a sus keys no se pierden debido a que en anteriores momentos copió sus datos a los primeros `k` nodos de la lista de `r` sucesores.  Cada cierto tiempo cada nodo le envía los últimos datos almacenados para replicar a uno de los `k` primeros nodos en su lista de sucesores. Cuando un nodo `A` se va de la red,  su predecesor `B` se da cuenta . El nodo `B` busca en su lista de sucesores  quien es el próximo sucesor vivo `C`, y le envía una  lista que significa que `C` debe encargarse de los datos del nodo `A`. Los  datos del nodo `A` estarán replicados en el nodo `C`, el cual pasará a poseer dichos datos como suyos, incluso para su posterior replicación en sus nodos sucesores.

#### Cliente:

