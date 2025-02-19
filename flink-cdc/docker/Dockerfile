FROM flink:1.19.1-java8

# Add Flink CDC files
ADD *.jar $FLINK_HOME/lib/
ADD flink-cdc*.tar.gz $FLINK_HOME/
RUN mv $FLINK_HOME/flink-cdc-3.3.0/lib/flink-cdc-dist-3.3.0.jar $FLINK_HOME/lib/