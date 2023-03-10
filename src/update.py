import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

class DatasetSplit(Dataset):
    def __init__(self, dataset, idxs):
        self.dataset = dataset
        self.idxs = [int (i) for i in idxs]

    def __len__(self):
        return len(self.idxs)

    def __getitem__(self,item): # image와 label을 tensor 타입을 얻는다.
        image, label = self.dataset[self.idxs[item]]
        return torch.tensor(image), torch.tensor(label)
        #return image.clone().detach(), label.clone().detach()
class LocalUpdate(object):
    def __init__(self, args, dataset, idxs, logger):
        self.args = args
        self.logger = logger
        self.trainloader, self.validloader, self.testloader = self.train_val_test(
            dataset, list(idxs)
        ) # data split과정
        self.device = 'cuda:0' #if args.gpu else 'cpu'
        # loss function은 NLL로 default
        self.criterion = nn.NLLLoss().to(self.device)

    def train_val_test(self, dataset, idxs):
        idxs_train = idxs[:int(0.8*len(idxs))]
        idxs_val = idxs[int(0.8*len(idxs)):int(0.9*len(idxs))]
        idxs_test = idxs[int(0.9*len(idxs)):]

        trainloader = DataLoader(DatasetSplit(dataset, idxs_train), # int(len(idxs_train)) self.args.local_bs
                                 batch_size=self.args.local_bs, shuffle=True)
        validloader = DataLoader(DatasetSplit(dataset, idxs_val),
                                 batch_size=int(len(idxs_val)/10), shuffle=False)
        testloader = DataLoader(DatasetSplit(dataset, idxs_test),
                                batch_size=int(len(idxs_test)/10),shuffle = False)

        return trainloader, validloader, testloader

    def update_weights(self, model, global_round):
        # train model
        model.train()
        epoch_loss=[]

        # optimizer 설정
        if self.args.optimizer == 'sgd':
            optimizer = torch.optim.SGD(model.parameters(), lr=self.args.lr, momentum=0.5)
        elif self.args.optimizer == 'adam':
            optimizer = torch.optim.Adam(model.parameters(),lr = self.args.lr, weight_decay = 1e-4)

        for iter in range(self.args.local_ep):
            batch_loss=[]
            for batch_idx, (images, labels) in enumerate(self.trainloader):
                images, labels = images.to(self.device), labels.to(self.device)

                model.zero_grad()
                log_probs = model(images)
                loss = self.criterion(log_probs, labels)
                loss.backward()
                optimizer.step()

                if self.args.verbose and (batch_idx % 10 == 0):
                    print('| Global Round : {} | Local Epoch : {} | [{}/{} ({:.0f}%)]\tLoss: {:.6f}'.format(
                        global_round, iter, batch_idx*len(images),
                        len(self.trainloader.dataset),
                        100.* batch_idx / len(self.trainloader), loss.item())
                    )
                self.logger.add_scalar('loss',loss.item())
                batch_loss.append(loss.item())
            epoch_loss.append(sum(batch_loss)/len(batch_loss))

        return model.state_dict(), sum(epoch_loss) / len(epoch_loss)

    def inference(self, model):
        """

        :param model:
        :return: inference accuracy and loss
        """

        model.eval()
        loss, total, correct = 0.0,0.0,0.0

        for batch_idx, (images, labels) in enumerate(self.testloader):
            images, labels = images.to(self.device), labels.to(self.device)

            # Inference
            outputs = model(images)
            batch_loss = self.criterion(outputs, labels)
            loss += batch_loss.item()

            # Prediction
            _, pred_labels = torch.max(outputs, 1)
            pred_labels = pred_labels.view(-1)
            correct += torch.sum(torch.eq(pred_labels, labels)).item()
            total += len(labels)

        accuracy = correct / total
        return accuracy, loss

def test_inference(args, model, test_dataset):
    model.eval()
    loss, total, correct = 0.0,0.0,0.0

    device = 'cuda:0' if args.gpu else 'cpu'
    criterion = nn.NLLLoss().to(device)
    testloader = DataLoader(test_dataset, batch_size=128, shuffle=False)

    for batch_idx, (images, labels) in enumerate(testloader):
        images, labels = images.to(device), labels.to(device)

        #inference
        output = model(images)
        batch_loss = criterion(output, labels)
        loss += batch_loss.item()

        #prediction
        _, pred_labels = torch.max(output,1)
        pred_labels = pred_labels.view(-1)
        correct += torch.sum(torch.eq(pred_labels, labels)).item()
        total += len(labels)

    accuracy = correct / total
    return accuracy, loss

