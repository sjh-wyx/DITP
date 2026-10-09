"""Docker 数据库初始化 — 种子用户 + 11 门课程 + 子任务 + Doris 表"""
import pymysql, os, time, json
from werkzeug.security import generate_password_hash

_MYSQL_HOST = os.getenv('MYSQL_HOST', 'mysql')
_MYSQL_PWD = os.getenv('MYSQL_PASSWORD', 'datatutor123')

def wait_mysql():
    for i in range(30):
        try:
            conn = pymysql.connect(host=_MYSQL_HOST, user='root', password=_MYSQL_PWD, port=3306, database='datatutor', connect_timeout=2)
            conn.close()
            print('[init] MySQL ready')
            return
        except: time.sleep(3)
    print('[init] MySQL timeout'); exit(1)

def wait_doris():
    for i in range(30):
        try:
            conn = pymysql.connect(host='doris', user='root', password='', port=9030, connect_timeout=3)
            cur = conn.cursor(); cur.execute('SHOW DATABASES'); cur.close(); conn.close()
            print('[init] Doris ready')
            return
        except: time.sleep(5)
    print('[init] Doris timeout')

# ── 1. MySQL 用户 ──
wait_mysql()
conn = pymysql.connect(host=_MYSQL_HOST, user='root', password=_MYSQL_PWD, port=3306, database='datatutor')
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM users')
if cur.fetchone()[0] == 0:
    for u in [
        ('tanwei', generate_password_hash('tanwei'), 'teacher', 'TW'),
        ('student1', generate_password_hash('123456'), 'student', 'student1'),
        ('stu001', generate_password_hash('123456'), 'student', 'stu001'),
        ('student2', generate_password_hash('123456'), 'student', 'student2'),
    ]:
        cur.execute('INSERT INTO users (username, password_hash, role, display_name) VALUES (%s,%s,%s,%s)', u)
    conn.commit()
    print('[init] 4 users created')

# ── 2. 11 门课程 + 子任务（先于班级关联，保证外键可用）──
cur.execute('SELECT COUNT(*) FROM courses')
if cur.fetchone()[0] == 0:
    courses = [
        (1, 'Hadoop 单机版环境搭建与 HDFS 基础操作实训', '掌握 Hadoop 伪分布式环境部署，包括 JDK 安装、SSH 免密登录、Hadoop 配置与 HDFS 文件操作', True),
        (2, 'MapReduce 分布式计算编程实战', '学习 MapReduce 编程模型，完成 WordCount、TopN、数据去重等经典案例', True),
        (3, 'Hive 数据仓库构建与 HQL 查询实战', '掌握 Hive 分区表设计、复杂 HQL 查询、UDF 开发与性能优化', True),
        (4, 'Spark 大数据处理与 RDD/DataFrame 编程', '学习 Spark Core 核心概念，掌握 RDD 转换操作、DataFrame API 与 Spark SQL', True),
        (5, 'Kafka 消息队列与 Flink 实时流处理', '搭建 Kafka 集群，学习生产者/消费者编程，结合 Flink 实现实时数据流处理', True),
        (6, 'ZooKeeper 分布式协调服务实战', '学习 ZK 集群搭建、节点操作、Watcher 机制与分布式锁实现', True),
        (7, 'HBase 分布式列式数据库入门与进阶', '掌握 HBase 表设计、RowKey 优化、Java API 编程与 BulkLoad 批量导入', True),
        (8, 'YARN 资源管理与作业调度', '深入理解 YARN 架构、Fair/Capacity Scheduler、队列配置与资源隔离', True),
        (9, 'Flume 日志采集与 Sqoop 数据迁移', '学习 Flume Source/Channel/Sink 配置，掌握 Sqoop RDBMS 与 HDFS/Hive 双向数据迁移', True),
        (10, 'Storm 实时计算与数据流拓扑', '搭建 Storm 集群，开发 Spout/Bolt 拓扑实现实时日志分析', True),
        (11, 'Impala 交互式查询与 Hue 可视化平台', '学习 Impala 实时 SQL 查询引擎，搭建 Hue Web 界面管理 Hive/HDFS/HBase', True),
    ]
    for cid, name, desc, pub in courses:
        cur.execute('INSERT INTO courses (id, teacher_id, name, description, is_public) VALUES (%s, 1, %s, %s, %s)', (cid, name, desc, pub))
    conn.commit()

    # 子任务数据
    all_subtasks = {
        1: [('基础环境准备',1,'java -version\nssh localhost exit','JDK 1.8+ 安装成功，SSH 免密登录正常','JDK 1.8 是 Hadoop 运行基础，SSH 免密登录用于 NameNode 远程管理 DataNode'),('下载并解压 Hadoop',2,'cd /opt && tar -xzf /home/learner/packages/hadoop-3.3.6.tar.gz -C /opt/','/opt/hadoop-3.3.6 目录存在','Hadoop 发行版包含 HDFS、MapReduce、YARN 三个核心组件'),('配置环境变量',3,'echo "export HADOOP_HOME=/opt/hadoop-3.3.6" >> ~/.bashrc\nsource ~/.bashrc\nhadoop version','hadoop version 显示 3.3.6','HADOOP_HOME 环境变量指向安装目录'),('修改 Hadoop 配置文件',4,'vi $HADOOP_HOME/etc/hadoop/core-site.xml\nvi $HADOOP_HOME/etc/hadoop/hdfs-site.xml','core-site.xml: fs.defaultFS=hdfs://localhost:9000','core-site.xml 配置默认文件系统，hdfs-site.xml 配置副本数'),('格式化 NameNode 并启动',5,'hdfs namenode -format\n$HADOOP_HOME/sbin/start-dfs.sh\njps','jps 显示 NameNode、DataNode 进程','NameNode 存储元数据，DataNode 存储实际数据块'),('HDFS 基础文件操作',6,'hdfs dfs -mkdir /user\nhdfs dfs -put /etc/hosts /user/\nhdfs dfs -ls /user/\nhdfs dfs -cat /user/hosts','文件上传成功，ls 可见 hosts 文件','HDFS 提供与 Linux 类似的命令行接口'),('验证 Web UI',7,'curl -s http://localhost:9870 | head -5','返回 NameNode Web UI HTML 页面','端口 9870 是 NameNode Web UI（3.x 版本）'),('副本机制测试',8,'hdfs dfs -setrep 2 /user/hosts\nhdfs fsck /user/hosts -files -blocks -locations','显示副本数为 2，Block 位置信息正常','默认 3 副本，伪分布式下实际只能存 1 份')],
        2: [('准备测试数据',1,'hdfs dfs -mkdir /input\nhdfs dfs -put /tmp/words.txt /input/','/input/words.txt 上传成功','MapReduce 输入数据存储在 HDFS 中'),('运行 WordCount',2,'hadoop jar $HADOOP_HOME/share/hadoop/mapreduce/hadoop-mapreduce-examples-3.3.6.jar wordcount /input /output','Map 100% Reduce 100%','WordCount 是 MapReduce 经典入门示例'),('查看结果',3,'hdfs dfs -cat /output/part-r-00000','hello 2, hadoop 2, world 2','Reduce 输出以 part-r- 开头'),('TopN 处理',4,'hdfs dfs -put /tmp/scores.txt /input/','成绩数据准备完成','TopN 需要自定义 Partitioner'),('Shuffle 分析',5,'hadoop job -history all | head -20','显示历史 Job 详情','Shuffle 涉及分区、排序、合并三个步骤'),('日志分析',6,'echo "访问 http://localhost:8088"','访问 YARN Web UI','YARN ResourceManager 管理集群资源')],
        3: [('Hive 安装',1,'cd /opt && tar -xzf /home/learner/packages/hive-4.0.0.tar.gz -C /opt/','Hive 安装包解压成功','Hive 将 SQL 转换为 MapReduce/Tez/Spark 作业'),('元数据库初始化',2,'schematool -dbType derby -initSchema','元数据表初始化成功','元数据存储表结构信息，Derby 仅用于测试'),('创建内部表',3,"hive -e 'CREATE TABLE employee (id INT, name STRING, salary DOUBLE) ROW FORMAT DELIMITED FIELDS TERMINATED BY \",\"'",'表 employee 创建成功','内部表数据存储在 /user/hive/warehouse'),('分区表设计',4,"hive -e 'CREATE TABLE logs (ip STRING, url STRING) PARTITIONED BY (dt STRING) ROW FORMAT DELIMITED FIELDS TERMINATED BY \" \"'",'分区表创建成功','分区表减少扫描数据量'),('复杂 HQL',5,"hive -e 'SELECT dept, AVG(salary) FROM employee GROUP BY dept HAVING AVG(salary) > 5000'",'各部门平均薪资 > 5000 的结果','HQL 支持 JOIN、GROUP BY、窗口函数'),('性能优化',6,"hive -e 'SET hive.exec.dynamic.partition.mode=nonstrict; SET mapreduce.map.memory.mb=2048'",'优化参数设置成功','动态分区 + 内存调优提升查询效率')],
        4: [('Spark 部署',1,'cd /opt && tar -xzf /home/learner/packages/spark-3.5.0-bin-hadoop3.tgz -C /opt/','/opt/spark-3.5.0 目录存在','Spark 比 MapReduce 快 100 倍（内存计算）'),('启动 Spark Shell',2,'$SPARK_HOME/bin/spark-shell --master local[2]','Spark context 初始化成功','spark-shell 是 Scala 交互式编程入口'),('RDD 操作',3,'val rdd = sc.textFile("/input/words.txt")\nrdd.flatMap(_.split(" ")).map(w=>(w,1)).reduceByKey(_+_).collect().foreach(println)','每个单词及出现次数','RDD 支持 transform 和 action 两类操作'),('DataFrame 编程',4,'val df = spark.read.option("header","true").csv("/data/employee.csv")\ndf.createOrReplaceTempView("emp")\nspark.sql("SELECT dept,COUNT(*) FROM emp GROUP BY dept").show()','各部门人数统计表','DataFrame 提供 Schema 约束'),('Spark SQL',5,"spark.sql('SELECT grade,AVG(score) FROM (SELECT CASE WHEN score>=90 THEN \"A\" WHEN score>=80 THEN \"B\" ELSE \"C\" END as grade,score FROM students) GROUP BY grade').show()",'各等级平均分','Spark SQL 支持窗函数、子查询'),('作业监控',6,'curl -s http://localhost:4040/api/v1/applications','正在运行的 Spark 应用列表','端口 4040 是 Spark Application UI')],
        5: [('Kafka 部署',1,'cd /opt && tar -xzf /home/learner/packages/kafka_2.13-3.7.0.tgz -C /opt/\n$KAFKA_HOME/bin/zookeeper-server-start.sh -daemon config/zookeeper.properties\n$KAFKA_HOME/bin/kafka-server-start.sh -daemon config/server.properties','Kafka Broker 启动','Kafka 依赖 Zookeeper 管理集群元数据'),('创建 Topic',2,'$KAFKA_HOME/bin/kafka-topics.sh --create --topic test-topic --bootstrap-server localhost:9092\n$KAFKA_HOME/bin/kafka-console-producer.sh --topic test-topic --bootstrap-server localhost:9092','Topic 创建成功','Topic 是消息的逻辑分类'),('消费者测试',3,'$KAFKA_HOME/bin/kafka-console-consumer.sh --topic test-topic --from-beginning --bootstrap-server localhost:9092','输出生产的所有消息','Consumer Group 实现负载均衡'),('Flink 部署',4,'cd /opt && tar -xzf /home/learner/packages/flink-1.19.0.tgz -C /opt/\n$FLINK_HOME/bin/start-cluster.sh','JobManager 和 TaskManager 启动成功','Flink 是真正的流处理引擎'),('Flink + Kafka',5,'$FLINK_HOME/bin/sql-client.sh\nCREATE TABLE source (...) WITH (connector=kafka)...\nSELECT window_start, COUNT(*) FROM source GROUP BY TUMBLE(ts, INTERVAL 10 SECOND)','每 10 秒输出窗口统计','Flink SQL 支持窗口聚合、CEP'),('监控面板',6,'curl -s http://localhost:8081/overview','Flink Dashboard JSON','端口 8081 是 Flink Web Dashboard')],
        6: [('ZK 集群搭建',1,'cd /opt && tar -xzf /home/learner/packages/zookeeper-3.9.2.tar.gz -C /opt/','ZK 安装包解压成功','ZooKeeper 使用 ZAB 协议保证分布式一致性'),('配置 zoo.cfg',2,'cd $ZK_HOME && cp conf/zoo_sample.cfg conf/zoo.cfg && echo "dataDir=/tmp/zk" >> conf/zoo.cfg','zoo.cfg 配置完成','tickTime、dataDir、clientPort 是核心配置'),('启动与连接',3,'$ZK_HOME/bin/zkServer.sh start\n$ZK_HOME/bin/zkCli.sh -server localhost:2181','Connected to ZooKeeper','ZK 默认端口 2181'),('节点操作',4,'create /data "hello"\nget /data\nset /data "world"\ndelete /data','数据节点创建、读取、修改、删除成功','ZK 数据模型类似文件系统'),('Watcher 机制',5,'stat -w /data\n# 在另一个终端修改 /data 观察通知','修改 /data 后收到 WatchedEvent 通知','Watcher 是一次性的'),('分布式锁实战',6,'create -e -s /lock/req- ""\nls /lock','临时顺序节点创建成功','ZK 分布式锁利用临时顺序节点 + Watch')],
        7: [('HBase 安装',1,'cd /opt && tar -xzf /home/learner/packages/hbase-2.5.8.tar.gz -C /opt/','HBase 安装完成','HBase 基于 HDFS 存储，依赖 ZK'),('配置 hbase-site.xml',2,'vi $HBASE_HOME/conf/hbase-site.xml\n<property><name>hbase.rootdir</name><value>hdfs://localhost:9000/hbase</value></property>','hbase-site.xml 配置完成','hbase.rootdir 指向 HDFS 存储路径'),('启动 HBase Shell',3,'$HBASE_HOME/bin/start-hbase.sh\n$HBASE_HOME/bin/hbase shell','HBase Shell 进入交互模式','jps 可见 HMaster、HRegionServer'),('创建表与数据操作',4,"create 'student','info','score'\nput 'student','001','info:name','Alice'\nget 'student','001'\nscan 'student'",'表创建、数据插入、查询成功','HBase 列族存储，RowKey 决定查询性能'),('RowKey 设计优化',5,'# 避免热点：用 Hash+时间戳做 RowKey\n# hash(138)12345678_timestamp','理解 RowKey 散列原理','好的 RowKey 避免 Region 热点'),('BulkLoad 批量导入',6,'hbase org.apache.hadoop.hbase.mapreduce.ImportTsv student /input/students.tsv','数据批量导入 HBase','BulkLoad 跳过 WAL，速度是 Put 的 10 倍')],
        8: [('理解 YARN 架构',1,'jps\n# 确认 ResourceManager、NodeManager 进程', 'RM 和 NM 进程运行中','YARN 解耦资源管理与作业调度'),('查看集群资源',2,'yarn node -list -all\nyarn application -list','显示节点资源和 Application','vCores 和 Memory 是 YARN 调度基本单位'),('队列配置',3,'vi $HADOOP_HOME/etc/hadoop/capacity-scheduler.xml\n# default=70%, dev=30%','capacity-scheduler.xml 配置完成','Capacity Scheduler 保证最低配额'),('提交到指定队列',4,'hadoop jar $HADOOP_HOME/share/hadoop/mapreduce/hadoop-mapreduce-examples-3.3.6.jar pi -Dmapreduce.job.queuename=dev 2 10','Pi 计算任务提交到 dev 队列','-Dmapreduce.job.queuename 指定队列'),('资源隔离测试',5,'hadoop jar ... -Dmapreduce.map.memory.mb=512 pi 5 10','任务以限制的内存运行','YARN 通过 Cgroup 实现资源隔离'),('RM Web UI',6,'curl -s http://localhost:8088/cluster/apps','YARN Web UI 应用列表','端口 8088 是 RM Web UI')],
        9: [('Flume 安装',1,'cd /opt && tar -xzf /home/learner/packages/flume-1.11.0.tar.gz -C /opt/','Flume 安装完成','Flume 采用 Source->Channel->Sink 三段式'),('配置 NetCat Source',2,'cat > $FLUME_HOME/conf/netcat.conf << EOF\na1.sources=r1\na1.channels=c1\na1.sinks=k1\na1.sources.r1.type=netcat\na1.sources.r1.bind=localhost\na1.sources.r1.port=44444\na1.channels.c1.type=memory\na1.sinks.k1.type=logger\nEOF','配置完成','Memory Channel 快但不持久化'),('Sqoop 安装',3,'cd /opt && tar -xzf /home/learner/packages/sqoop-1.4.7.tar.gz -C /opt/','Sqoop 安装完成','Sqoop 将 MapReduce 翻译为 JDBC 查询'),('MySQL→HDFS 导入',4,'sqoop import --connect jdbc:mysql://localhost/datatutor --table users --username root --password "" --target-dir /sqoop/users -m 1','users 表导入 /sqoop/users','-m 1 用一个 MapTask'),('HDFS→MySQL 导出',5,'sqoop export --connect jdbc:mysql://localhost/datatutor --table export_results --export-dir /output/part-r-00000 --username root --password "" -m 1','HDFS 数据导出到 MySQL','Sqoop Export 将 HDFS 写入 RDBMS'),('Flume→Kafka→HDFS 管道',6,'# Source: netcat -> Channel: memory -> Sink: hdfs\n# hdfs://localhost:9000/flume/%Y%m%d','端到端管道搭建成功','Flume 支持多种 Source/Sink')],
        10: [('Storm 安装',1,'cd /opt && tar -xzf /home/learner/packages/storm-2.6.1.tar.gz -C /opt/','Storm 安装完成','Nimbus + Supervisor + ZK'),('启动 Storm 集群',2,'$STORM_HOME/bin/storm nimbus &\n$STORM_HOME/bin/storm supervisor &\n$STORM_HOME/bin/storm ui &','jps 可见 nimbus、supervisor','Nimbus 主节点，Supervisor 工作节点'),('开发 Spout',3,'# Java: RandomSentenceSpout extends BaseRichSpout\n# nextTuple() 随机发射句子','Spout 持续产生随机句子','Spout 是拓扑的数据输入源'),('开发 Bolt',4,'# Java: SplitBolt extends BaseRichBolt\n# execute() 分割单词并发射','Bolt 编译通过','Bolt 处理输入 Tuple'),('提交拓扑',5,'$STORM_HOME/bin/storm jar wordcount.jar WordCountTopology','拓扑提交成功','拓扑持续运行直到手动 Kill'),('Storm UI 监控',6,'curl -s http://localhost:8080/api/v1/topology/summary','运行中的拓扑列表','端口 8080 是 Storm UI')],
        11: [('Impala 安装',1,'cd /opt && wget https://archive.apache.org/dist/impala/4.4.0/apache-impala-4.4.0.tar.gz && tar -xzf apache-impala-4.4.0.tar.gz','Impala 安装完成','MPP 架构，直接读取 HDFS/HBase'),('启动 Impala',2,'$IMPALA_HOME/bin/start-impala-cluster.py\n# 检查 impalad 进程','impalad 进程运行中','Impala 不依赖 MapReduce'),('Impala SQL',3,"impala-shell -q 'SELECT dept, COUNT(*), AVG(salary) FROM employee GROUP BY dept'",'查询秒级返回','Impala 兼容 HiveQL'),('Hue 安装',4,'cd /opt && wget https://github.com/cloudera/hue/archive/refs/tags/release-4.11.0.tar.gz -O hue.tar.gz && tar -xzf hue.tar.gz','Hue 安装完成','Hadoop 生态 Web UI 管理平台'),('Hue 连接 Hive/HDFS',5,'vi $HUE_HOME/desktop/conf/hue.ini\n# hive_server_host=localhost\n# fs_defaultfs=hdfs://localhost:9000','访问 http://localhost:8888','Hue 支持 Hive、Impala、HDFS、HBase'),('Impala vs Hive 对比',6,'# Hive: ~30s | Impala: ~2s','Impala 比 Hive 快 15 倍','Impala 适合交互分析，Hive 适合批处理')],
    }
    for cid, subtasks in all_subtasks.items():
        for name, idx, cmd, expect, knowledge in subtasks:
            cur.execute('INSERT INTO subtasks (course_id, order_index, name, command, expected_output, knowledge_text) VALUES (%s,%s,%s,%s,%s,%s)', (cid, idx, name, cmd, expect, knowledge))
    conn.commit()
    cur.execute('SELECT COUNT(*) FROM subtasks')
    print(f'[init] {cur.fetchone()[0]} subtasks across 11 courses')

# ── 1.5 班级种子（班级-课程多对多，依赖 courses 已插入）──
cur.execute('DELETE FROM class_students')
cur.execute('DELETE FROM classes')
conn.commit()
cur.execute('SELECT COUNT(*) FROM classes')
if cur.fetchone()[0] == 0:
    cur.execute("INSERT INTO classes (teacher_id, name, class_code) VALUES (1, '大数据一班', 'BD2024-01')")
    class_id = cur.lastrowid
    for cid in range(1, 12):
        cur.execute('INSERT INTO class_courses (class_id, course_id) VALUES (%s, %s)', (class_id, cid))
    conn.commit()
    print(f'[init] 1 class + 11 course associations')

cur.close(); conn.close()

# ── 3. Doris 表（本地无 Doris 时通过 SKIP_DORIS=1 跳过）──
if os.getenv('SKIP_DORIS') != '1':
    wait_doris()
    conn = pymysql.connect(host='doris', user='root', password='', port=9030)
    cur = conn.cursor()
    cur.execute('CREATE DATABASE IF NOT EXISTS datatutor_analytics')
    cur.execute('USE datatutor_analytics')
    for sql in [
        'CREATE TABLE IF NOT EXISTS terminal_events (student_id INT, event_time DATETIME DEFAULT CURRENT_TIMESTAMP, course_id INT, subtask_id INT, vm_name VARCHAR(50), data STRING, direction VARCHAR(10)) DUPLICATE KEY(student_id, event_time) DISTRIBUTED BY HASH(student_id) BUCKETS 2 PROPERTIES("replication_num"="1")',
        'CREATE TABLE IF NOT EXISTS chat_events (student_id INT, event_time DATETIME DEFAULT CURRENT_TIMESTAMP, course_id INT, subtask_id INT, msg_role VARCHAR(10), msg_length INT) DUPLICATE KEY(student_id, event_time) DISTRIBUTED BY HASH(student_id) BUCKETS 2 PROPERTIES("replication_num"="1")',
        'CREATE TABLE IF NOT EXISTS task_completions (student_id INT, event_time DATETIME DEFAULT CURRENT_TIMESTAMP, course_id INT, subtask_id INT, duration_seconds INT, grade_level VARCHAR(2)) DUPLICATE KEY(student_id, event_time) DISTRIBUTED BY HASH(student_id) BUCKETS 2 PROPERTIES("replication_num"="1")',
        'CREATE TABLE IF NOT EXISTS page_views (student_id INT, event_time DATETIME DEFAULT CURRENT_TIMESTAMP, page VARCHAR(100), duration_seconds INT) DUPLICATE KEY(student_id, event_time) DISTRIBUTED BY HASH(student_id) BUCKETS 2 PROPERTIES("replication_num"="1")',
    ]:
        try: cur.execute(sql)
        except Exception as e: print(f'[init] Doris warn: {str(e)[:60]}')
    conn.commit()
    cur.close(); conn.close()
    print('[init] Doris tables created')
print('[init] All done — 4 users + 11 courses + 68 subtasks + 4 Doris tables')
