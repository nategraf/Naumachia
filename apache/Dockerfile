FROM php:7.0-apache
RUN apt-get update && \
    apt-get install -y php5-mysqlnd && \
    docker-php-ext-install -j$(nproc) mysqli
ADD ./www /var/www/html
ADD ./config/php /usr/local/etc/php
