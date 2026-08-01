// LEGACY — superseded by .github/workflows/ci.yml (GitHub Actions).
// Kept as a documented secondary / historical pipeline for the CA2 narrative.
// Do not use this file for the FA live demo path.
pipeline {
    agent any

    environment {
        IMAGE_REPOSITORY = 'docker.io/YOUR_DOCKERHUB_USERNAME/c270-hotel-management'
        IMAGE_TAG = "${BUILD_NUMBER}"
        MYSQL_DATABASE = 'hotel_management_test'
        MYSQL_USER = 'hotel_test'
        MYSQL_PASSWORD = 'hotel_test_password'
        FLASK_SECRET_KEY = 'ci-only-secret-not-for-production'
    }

    stages {
        stage('Checkout') {
            steps { checkout scm }
        }

        stage('Test') {
            steps {
                sh '''#!/bin/sh
                    docker network create hotel-ci 2>/dev/null || true
                    docker rm -f hotel-ci-mysql 2>/dev/null || true
                    docker run -d --name hotel-ci-mysql --network hotel-ci \\
                      -e MYSQL_DATABASE=$MYSQL_DATABASE \\
                      -e MYSQL_USER=$MYSQL_USER \\
                      -e MYSQL_PASSWORD=$MYSQL_PASSWORD \\
                      -e MYSQL_ROOT_PASSWORD=ci-root-password \\
                      mysql:8.4
                    until docker exec hotel-ci-mysql mysqladmin ping -h localhost -uroot -pci-root-password --silent; do sleep 2; done
                    docker run --rm --network hotel-ci \\
                      -e FLASK_SECRET_KEY=$FLASK_SECRET_KEY \\
                      -e MYSQL_HOST=hotel-ci-mysql -e MYSQL_PORT=3306 \\
                      -e MYSQL_USER=$MYSQL_USER -e MYSQL_PASSWORD=$MYSQL_PASSWORD \\
                      -e MYSQL_DATABASE=$MYSQL_DATABASE -e MYSQL_TEST_DATABASE=$MYSQL_DATABASE \\
                      -v "$WORKSPACE:/app" -w /app python:3.11-slim \\
                      sh -c 'pip install --no-cache-dir -r requirements.txt && pytest -q'
                '''
            }
            post { always { sh 'docker rm -f hotel-ci-mysql 2>/dev/null || true' } }
        }

        stage('Build image') {
            steps { sh 'docker build --tag $IMAGE_REPOSITORY:$IMAGE_TAG --tag $IMAGE_REPOSITORY:latest .' }
        }

        stage('Publish image') {
            when { branch 'main' }
            steps {
                withCredentials([usernamePassword(credentialsId: 'dockerhub-credentials', usernameVariable: 'DOCKERHUB_USERNAME', passwordVariable: 'DOCKERHUB_TOKEN')]) {
                    sh '''#!/bin/sh
                        echo "$DOCKERHUB_TOKEN" | docker login -u "$DOCKERHUB_USERNAME" --password-stdin
                        docker push $IMAGE_REPOSITORY:$IMAGE_TAG
                        docker push $IMAGE_REPOSITORY:latest
                    '''
                }
            }
        }

        stage('Deploy') {
            when { branch 'main' }
            steps {
                withCredentials([sshUserPrivateKey(credentialsId: 'hotel-production-ssh', keyFileVariable: 'SSH_KEY', usernameVariable: 'SSH_USER')]) {
                    sh '''#!/bin/sh
                        ssh -i "$SSH_KEY" -o StrictHostKeyChecking=yes "$SSH_USER@$DEPLOY_HOST" \\
                          "cd /opt/c270-hotel-management && IMAGE_NAME=$IMAGE_REPOSITORY:$IMAGE_TAG docker compose pull app && IMAGE_NAME=$IMAGE_REPOSITORY:$IMAGE_TAG docker compose up -d app"
                    '''
                }
            }
        }
    }
}
